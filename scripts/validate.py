"""The checker: the person's workbench for the motif index, and the other curation pages, on a small local server
that is never part of the site or deployed (#121; it began as a headline label check, now scripts/checker/labels.py).

Run as a service (deploy/systemd/maudlin-checker.service), or by hand, and open http://<this machine>:8766 on any
device on the network. Pages are Jinja templates in scripts/checker/templates with shared scripts in
scripts/checker/static. Every change to the motif index comes in as a named action (app/analysis/motif_actions.py),
is logged with what it replaced (validation/curation_log.jsonl) and can be undone. GET_JSON lists the data each page
reads.

    .venv/bin/python scripts/validate.py [--port 8766] [--follow-code]
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime as dt, timedelta as td
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import Config  # noqa: E402

# The pages: Jinja templates in checker/templates (one base with the shared nav and undo), shared scripts and styles
# in checker/static (the drag-with-drop-zones and undo code), served at /checker/static/
CHECKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checker')
# files the checker shares with the site, served from the site's static folder (the motif maps' layout)
SHARED_STATIC = {'motif-map-layout.js': os.path.join(os.path.dirname(CHECKER), '..', 'app', 'site', 'static', 'motif-map-layout.js')}
# The nav: the workbench and the map first (the two the person works in), then the older single-purpose motif pages,
# then the other tools. The organizer, the singles page and the board were dropped Oct 7 (the workbench does their
# work; the board's /motif-board.json and POST /motif-board stay, for the map and the other pages). (path, label, section)
NAV = [('/motif-workbench', '🧰 Motif workbench', 'main'), ('/motif-map', '🕸️ Motif map', 'main'),
       ('/dashboard', '📈 Dashboard', 'main'), ('/experiments', '🧪 Experiments', 'main'), ('/flow', '🌊 Flow', 'main'), ('/live', '🧠 Live', 'main'),
       ('/motifs', '✅ check', 'motifs'), ('/motif-empty', '🫙 empty', 'motifs'),
       ('/motif-notes', '📝 notes', 'motifs'),
       ('/', '🏷️ label check', 'other'), ('/entities', '👥 names', 'other'), ('/ui/', '⚛️ new checker', 'other')]
_templates = None


def experiments_lab():
    """scripts/experiments/lab.py, the experiments page's data, imported from this checkout"""
    import sys
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiments')
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import lab
    return lab


def render(template: str, here: str, undo: bool = True, **context) -> str:
    """A checker page from its template: `here` is its path in the nav; `undo` adds the undo button (every
    organizer page; the label check writes the database instead)."""
    global _templates
    if _templates is None:
        from jinja2 import Environment, FileSystemLoader
        _templates = Environment(loader=FileSystemLoader(os.path.join(CHECKER, 'templates')), autoescape=True)
    return _templates.get_template(template).render(nav=NAV, here=here, undo=undo, **context)


STATIC_PAGES = {'/motif-workbench': 'workbench.html', '/motif-map': 'map.html', '/motif-empty': 'empty.html',
                '/motif-notes': 'notes.html', '/dashboard': 'dashboard.html', '/experiments': 'experiments.html',
                '/flow': 'flow.html', '/live': 'live.html'}
STATIC_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}


FOLDER = os.path.join(Config.data, 'validation')


def _checker_module(name: str):
    """A module of the checker's own (scripts/checker/<name>.py), loaded by path like this file is"""
    import importlib.util
    if name not in _modules:
        spec = importlib.util.spec_from_file_location(f'checker_{name}', os.path.join(CHECKER, f'{name}.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules[name] = module
    return _modules[name]


_modules = {}
labels = _checker_module('labels')  # 🏷️ the headline label check, the page this tool began as (#121)


MOTIF_VERDICTS = os.path.join(FOLDER, 'motif_verdicts.jsonl')  # a record of every answer, for agreement scores
MOTIF_BATCH = 10


def motif_page() -> str:
    """The motif check: is each claim filed in our motif index an instance of its motif? Answers apply at once."""
    from app.analysis import motif_index
    return render('motif_check.html', '/motifs', todo=motif_index.to_check(), batch=MOTIF_BATCH)


CURATION_LOG = os.path.join(FOLDER, 'curation_log.jsonl')  # every correction, with what the model had proposed


def motif_context(data: dict) -> dict:
    """What the model had proposed before a person's change: each motif the action names (its name, whether the model
    or a person made it, a few of its claims) and, for a claim, every motif it was filed under."""
    from app.analysis import motif_index as mi
    index = mi.snapshot()  # read only
    entries = index['entries']

    def motif(eid):
        e = entries.get(eid)
        return e and {'id': eid, 'name': e['name'], 'by': 'person' if e.get('curated') else 'model',
                      'note': e.get('note', ''), 'note_by': e.get('note_by', ''),  # a draft rewritten: the pair kept
                      'claims': [c['claim'] for c in e['claims'][:8]], 'size': len(e['claims'])}
    out = {k: motif(data[k]) for k in ('id', 'source', 'target', 'a', 'b', 'child', 'parent') if isinstance(data.get(k), str) and data[k] in entries}
    claim = data.get('claim')
    if isinstance(claim, str) and claim:
        out['claim_motifs'] = [motif(i) | {'claims': None} for i in mi._ids(index, mi.key(claim)) if i in entries]
    return out


def decision_fits(data: dict) -> dict:
    """The confidence model's fit, at this moment, for each filing an action names (claim key|motif id), and where its
    'sure' began: kept in the log's 'before', so the dashboard can tell how often the model called the person's
    decisions right (Oct 9)"""
    from app.analysis import filing_confidence as fc, motif_index as mi
    from app.utils.store import read_json
    entries = mi.snapshot()['entries']  # read only
    fits = {}
    for s in [data] + [x for x in (data.get('steps') or []) if isinstance(x, dict)]:
        pairs = [(s.get('claim'), s.get(k)) for k in ('id', 'source', 'target')]
        pairs += [(x.get('claim'), x.get('source')) for x in (s.get('claims') or []) if isinstance(x, dict)]
        for c, eid in pairs:
            if isinstance(c, str) and isinstance(eid, str) and eid in entries:
                fit = next((x.get('fit') for x in entries[eid]['claims'] if x['claim'] == c), None)
                if fit is not None:
                    fits[f'{mi.key(c)}|{eid}'] = fit
    if not fits:
        return {}
    return {'fits': fits, 'sure_at': ((read_json(fc.MODEL, None) or {}).get('test') or {}).get('sure_at')}


BY = {'claude'}  # who besides the person may act through the checker (by MCP, scripts/maudlin_mcp.py), marked as theirs


def log_curation(page: str, data: dict, before: dict, by: str | None = None):
    os.makedirs(FOLDER, exist_ok=True)
    at = dt.now().isoformat(timespec='seconds')
    with open(CURATION_LOG, 'a') as f:
        f.write(json.dumps({'at': at, 'page': page, 'action': data, 'before': before, **({'by': by} if by else {})}) + '\n')
    from app.analysis import curation_db  # and in the curation database (Oct 8)
    curation_db.record_action(at, page, data, before, by)


# Undo: each change on the organizer pages snapshots the file it touched (the motif index, or the name aliases) so the
# last ones can be stepped back, newest first. Kept on disk, so a server restart doesn't lose them.
UNDO = os.path.join(FOLDER, 'undo')
UNDO_KEEP = 50


def undo_paths() -> dict:
    from app.analysis import entities, motif_index
    return {'/motif-board': motif_index.INDEX, '/motif-verdict': motif_index.INDEX,
            '/workbench': motif_index.INDEX,
            '/entities': entities.ALIASES}


def read_text(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def state(path: str) -> str | None:
    """What a step's undo keeps of a file it manages: the file's text, or for the motif index (a database since Oct 21)
    the number of its last save ('txn:41'), since undo takes back the rows changed after it"""
    from app.analysis import motif_index as mi
    if path == mi.INDEX:
        return f'txn:{mi.version()}' if not mi._json_mode() else read_text(mi.legacy())
    return read_text(path)


def restore(path: str, before: str | None):
    """Put a managed file back as `state` found it (the caller holds the index's lock)"""
    from app.analysis import motif_index as mi, motif_db
    if path == mi.INDEX and (before or '').startswith('txn:'):
        motif_db.revert(mi.INDEX, int(before[4:]))
        return
    if path == mi.INDEX:
        path = mi.legacy()
    with open(path + '.tmp', 'w') as f:
        f.write(before or '')
    os.replace(path + '.tmp', path)


def describe(data: dict, before: dict) -> str:
    """'merge “Government deception” into “False flag operation”' and the like, for the undo button"""
    name = lambda k: (before.get(k) or {}).get('name') or data.get(k)  # noqa: E731
    act = data.get('action') or ('motif check: ' + str(data.get('answer')))
    if act == 'proposal_reject':
        act = 'reject a proposal'
    elif data.get('proposal'):
        act = 'approve a proposal: ' + act
    parts = [act] + [f'“{name(k)}”' for k in ('source', 'id', 'a', 'child') if data.get(k)]
    parts += [f'→ “{name(k)}”' for k in ('target', 'b', 'parent') if data.get(k)]
    if data.get('name'):
        parts.append(f'as “{data["name"]}”')
    if data.get('text'):
        parts.append(f'to “{data["text"][:80]}”')
    return ' '.join(parts)[:160]


def push_undo(path: str, before_text: str | None, what: str, proposals: list[str] | None = None):
    """A step to undo: the file as it was, and the proposals the step decided (reopened on undo; a rejection changes
    no file but is a step all the same; until Oct 7 undo skipped it, and undoing an approval left it decided)"""
    after = state(path)
    if after == before_text and not proposals:
        return
    os.makedirs(UNDO, exist_ok=True)
    stamp = dt.now().strftime('%Y%m%d-%H%M%S-%f')
    with open(os.path.join(UNDO, stamp + '.json'), 'w') as f:
        json.dump({'path': path, 'before': before_text, 'after_sha': hashlib.sha1((after or '').encode()).hexdigest(),
                   'what': what, 'at': stamp, **({'proposals': proposals} if proposals else {})}, f)
    for old in sorted(os.listdir(UNDO))[:-UNDO_KEEP]:
        os.remove(os.path.join(UNDO, old))


def last_undo() -> tuple[str, dict] | None:
    try:
        names = sorted(n for n in os.listdir(UNDO) if n.endswith('.json'))
    except OSError:
        return None
    managed = set(undo_paths().values())
    for name in reversed(names):  # only snapshots of the files undo manages (a stray one from elsewhere is skipped)
        path = os.path.join(UNDO, name)
        with open(path) as f:
            snap = json.load(f)
        if snap.get('path') in managed:
            return path, snap
    return None


def undo() -> str:
    """Step back the newest change; refuses if the file changed since (an hourly run filing claims), rather than
    losing that"""
    from app.analysis import motif_index
    found = last_undo()
    if not found:
        raise ValueError('nothing to undo')
    snap_path, snap = found
    with motif_index.locked():
        now = state(snap['path']) or ''
        if hashlib.sha1(now.encode()).hexdigest() != snap['after_sha']:
            raise ValueError('the index has changed since that edit (an hourly run filing claims?), so undoing it '
                             'would lose those changes: fix it by hand instead')
        restore(snap['path'], snap['before'])
    os.remove(snap_path)
    if snap.get('proposals'):
        from app.analysis import motif_proposals
        motif_proposals.reopen(snap['proposals'])
    log_curation('undo', {'action': 'undo', 'undid': snap['what']}, {})
    return snap['what']


SHOW_NEAR = 0.8  # likeness (mxbai) for a show claim to count as a telling of a claim filed in other words


def nearest_tellings(words: set[str], n: int = 5) -> list[dict]:
    """The show claims closest in meaning to a claim's words, at SHOW_NEAR or above (the retold groups' own
    likeness), when none matches them word for word"""
    import numpy as np
    from app.analysis import show_claims
    from app.narratives import embed
    told = [dict(c, show=e['show'], url=url) for url, e in show_claims.load().items() for c in e.get('claims', [])]
    if not told or not words:
        return []
    v = embed(sorted(words) + [t['claim'] for t in told])
    q, rest = v[:len(words)], v[len(words):]
    best = (rest @ q.T).max(1)
    order = [i for i in np.argsort(-best)[:n] if best[i] >= SHOW_NEAR]
    return [told[i] for i in order]


def show_tellings(words: set[str]) -> list[dict]:
    """Every telling of a claim retold across the shows (show_claims.kept_retold, the group whose claim is one of
    `words`): the show, its lean, the episode, who said it, about when, the quote and the transcript around it"""
    from app.analysis import focus_group, show_claims
    group = next((r for r in show_claims.kept_retold() if r['claim'] in words), None)
    if group is None:  # not in the last run's groups: its own episode's claims, at least
        group = {'told': [dict(c, show=e['show'], url=url) for url, e in show_claims.load().items()
                          for c in e.get('claims', []) if c['claim'] in words]}
    if not group['told']:  # filed in one telling's words or reworded, and its group since gone (Oct 20: "The left
        group = {'told': nearest_tellings(words)}  # should adopt the identity of a fighter" showed no origin at all)
    episodes = show_claims.load()
    out = []
    for t in group.get('told', []):
        ep = episodes.get(t['url'], {})
        try:
            around = focus_group.context(t['url'], t.get('quote', ''))
        except Exception:  # noqa: BLE001 - the telling stands without it
            around = None
        out.append({'show': t['show'], 'lean': ep.get('lean'), 'title': ep.get('title'), 'date': ep.get('date'),
                    'url': t['url'] if t['url'].startswith('http') else None, 'speaker': t.get('speaker') or '',
                    'at': t.get('at'), 'claim': t.get('claim'), 'quote': t.get('quote'), 'context': around})
    return sorted(out, key=lambda t: (t['date'] or '', t['show']), reverse=True)


def save_checkpoint(name: str, kind: str = 'manual') -> dict:
    """The motif index and the proposals as they are now, saved by name in the curation database, to go back to"""
    from app.analysis import curation_db, motif_index as mi, motif_proposals as mp
    with mi.locked():
        return curation_db.checkpoint(name, mi.export_text(), read_text(mp.PROPOSALS), kind)


def go_back(cid: int) -> dict:
    """The motif index and proposals put back as checkpoint `cid` saved them. What's there now is saved first (a
    checkpoint 'before going back'), so this can itself be gone back on, and it's one undo step too; the changes since
    the checkpoint stay in the log, marked reverted, so the models stop learning from them"""
    from app.analysis import curation_db, motif_index as mi, motif_proposals as mp
    from app.utils.store import write_json
    cp, index_text, proposals_text = curation_db.restore(cid)
    with mi.locked():
        now_state, now_proposals = state(mi.INDEX), read_text(mp.PROPOSALS)
        before = curation_db.checkpoint(f'before going back to “{cp["name"]}”', mi.export_text(), now_proposals,
                                        kind='before going back')
        mi.save(json.loads(index_text))
        if proposals_text is not None:
            write_json(mp.PROPOSALS, json.loads(proposals_text))
    undone = curation_db.set_reverted(cp)
    push_undo(mi.INDEX, now_state, f'go back to “{cp["name"]}”')
    log_curation('checkpoints', {'action': 'go back', 'to': cid, 'name': cp['name'], 'reverted': undone,
                                 'saved_first': before['id']}, {})
    return {'to': cp, 'reverted': undone, 'saved_first': before}


def claim_detail(claim: str) -> dict:
    """What's behind a claim for the motif board: the fact-check it came from (headline, summary, link, the model's
    labels) or the folklore group (how many told it, a few of their posts, linked articles, labels). Local only."""
    from app.analysis import factchecks, motif_index as mi
    index = mi.snapshot()
    words = mi.originals(claim, index)
    filed = next((c for e in mi.live(index) for c in e['claims'] if c['claim'] == claim), {})
    out = {'claim': claim, 'source': filed.get('source', ''), 'model_words': sorted(words - {claim})}
    if filed.get('split_from'):  # one telling (a side) split out of a claim: where it came from is where that came
        out['split_from'] = filed['split_from']  # from (Oct 20: the Biden side of a dispute showed "report is gone")
        words = words | mi.originals(filed['split_from'], index)
    if filed.get('source') == 'Focus Group':
        from app.analysis import focus_group
        ep = focus_group.load().get(filed.get('ref', ''), {})
        said = next((c for c in ep.get('claims', []) if c['claim'] in words), {})
        out.update(kind='focus-group', title=ep.get('title'), url=filed.get('ref'), published=ep.get('date', ''),
                   quote=said.get('quote'), side=said.get('side'), at=said.get('at'))
        try:  # the transcript around the quote, to read it in
            out['context'] = focus_group.context(filed.get('ref', ''), said.get('quote', ''))
        except Exception:  # noqa: BLE001 - the detail stands without it
            out['context'] = None
        return out
    from app.analysis import show_claims
    if filed.get('source') == show_claims.SOURCE:  # told on two or more shows: every telling, with its transcript
        out.update(kind='radio & podcasts', tellings=show_tellings(words))
        return out
    if filed.get('source') and filed['source'] != 'narrative':
        url = filed.get('ref', '')
        item = next((i for i in factchecks._items(90) if i.get('url') == url), {})
        try:
            with open(os.path.join(Config.data, 'factcheck_labels.json')) as f:
                label = json.load(f).get(url, {})
        except (OSError, ValueError):
            label = {}
        from app.analysis import factcheck_text
        out.update(kind='fact-check', url=url, title=item.get('title'), summary=item.get('summary'),
                   published=(item.get('published') or '')[:10], label=label,
                   piece=factcheck_text.text_of(url)[:2500])  # the piece's own opening, read by the hourly run
        return out
    # The narrative report the claim came from (its ref is the report's time), else the latest, else any that has it
    import glob
    from app.narratives import FOLDER
    reports = sorted(glob.glob(os.path.join(FOLDER, 'report-*.json')), reverse=True)
    ref = filed.get('ref', '').replace('-', '').replace('T', '-').replace(':', '')  # 2026-10-05T08:17 -> 20261005-0817
    ordered = [r for r in reports if os.path.basename(r)[7:20].replace('-', '', 2) == ref] + reports
    group, report = None, {}
    for path in ordered:
        try:
            with open(path) as f:
                report = json.load(f)
        except (OSError, ValueError):
            continue
        group = next((g for g in report.get('found', []) if (g.get('label') or {}).get('narrative') in words), None)
        if group:
            break
    if group:
        from app.narratives import posts_of
        every = posts_of(group.get('keys') or [])  # every post in it, where the report kept them (Oct 6 on)
        out.update(kind='folklore', made=report.get('made'), people=group.get('authors'), posts=group.get('posts'),
                   examples=[str(x)[:400] for x in (group.get('examples') or [])[:6]],
                   all_posts=[{**p, 'text': p['text'][:500]} for p in every],
                   articles=[a if isinstance(a, dict) else {'title': str(a)} for a in (group.get('articles') or [])[:5]],
                   label=group.get('label') or {})
    else:
        out['kind'] = 'folklore (its report is gone)'
    return out


def board_action(data: dict):
    """One change from the motif board, the map or the notes page: the same actions as the workbench's"""
    workbench_action(data)


# The motif workbench (workbench.html): one page for everything the motif pages do. Its state is the board's plus
# what only other pages had (stands alone, checks to do); its actions are the board's plus 'not the same', the motif
# check, and a batch of several (one undo step for a whole multi-select drag)
def workbench_state() -> dict:
    from app.analysis import motif_index as mi
    index = mi.snapshot()  # read once and passed on (Oct 22: it was read four times a state, the log four times too)
    state = mi.board(index)
    for e in state['entries']:
        entry = index['entries'].get(e['id'], {})
        e['stands_alone'] = bool(entry.get('stands_alone'))
        e['watch'] = bool(entry.get('watch'))
        e['phrases'] = (entry.get('phrases') or [])[:6]
        e['carrying'] = mi.carrying(entry)[:12]  # its phrase dictionary so far, from the filings' carrying words
    state['to_check'] = sum(1 for e in mi.live(index) for c in e['claims'] if not c.get('checked'))
    hand, recent = hand_made(), recently_confirmed()
    state['second_look'] = sum(1 for e in mi.live(index) for c in e['claims'] if doubted(e, c, hand, recent))
    state['not_same'] = [sorted(p) for p in index.get('not_same', [])]
    state['facets'] = mi.facet_values(index)
    # the claims on hold, in the words their filings carry now: out of the queues, in the ⏸ held tab
    held = mi.held(index)
    state['held'] = sorted({c['claim'] for e in mi.live(index) for c in e['claims'] if mi.key(c['claim']) in held})
    from app.analysis import motif_proposals as mp
    state['proposals'] = len(mp.open_proposals(index))  # the 💡 tab's count
    from app.analysis import claim_organizer as co
    state['splits'] = sum(1 for p in mp.load().values() if p.get('status') == 'open' and co.still_holds(p, index))
    from app.analysis import tellings
    drafted = tellings.drafted(index)
    state['tellings'] = sum(len(m['tellings']) for m in drafted)
    state['tellings_of'] = {m['id']: len(m['tellings']) for m in drafted}  # a motif panel's 🧩 button
    from app.analysis import filing_confidence as fc
    from app.utils.store import read_json
    m = read_json(fc.MODEL, None)  # how sure 'sure' is, as tested held out
    sure = m and m['test'].get('sure_at')
    state['confidence'] = {'sure_at': sure, 'auc': m['test']['auc'],
                           'at_sure': next((t for t in m['test']['thresholds'] if t['at'] == sure), None),
                           # the likely-out line, and how often the person took out what fell under it (from the
                           # model trained after Oct 18; the line alone before)
                           'out_at': fc.OUT_AT, 'at_out': m['test'].get('at_out'),
                           'tally': sure_tally(index=index)} if sure else None
    return state


def filing_fits() -> dict:
    """Each unchecked filing's fit, as the hourly run left it on the filing (filing_confidence.refresh: the checker
    never asks the models itself)"""
    from app.analysis import motif_index as mi
    return {f"{mi.key(c['claim'])}|{e['id']}": c['fit'] for e in mi.live(mi.snapshot()) for c in e['claims']
            if not c.get('checked') and c.get('fit') is not None}


def check_queue() -> list[dict]:
    """Every filing nobody has checked, each with its fit (the chance the person keeps it; only in their own motifs),
    the claims the model is least sure of first (a fit nearest even, by the claim's least likely filing): E6 (Oct 9)
    found the person's checks teach it most in that order, 150 of them as much as ~550 at random or more likeliest
    first (the order before). The sure ones still pass in one step from their own fold"""
    from app.analysis import filing_confidence as fc, motif_index as mi
    items = mi.to_check()
    fits = filing_fits()
    index = mi.snapshot()
    tested = fc.tested_sources(index) if fits else set()
    for x in items:
        x['fit'] = fits.get(f"{mi.key(x['claim'])}|{x['id']}")
        x['can_be_sure'] = fc.can_be_sure(index, x['claim'], x['id'], x.get('source', ''), tested)
    if not fits:
        return items  # the old order: biggest motifs first (all of them: capped at 40, the rest went unseen)
    # a claim's place: its least likely filing in your motifs; one only in the model's own motifs (no fit) goes last
    least = {}
    for x in items:
        if x['fit'] is not None:
            least[x['claim']] = min(least.get(x['claim'], 1.0), x['fit'])
    return sorted(items, key=lambda x: (abs(least[x['claim']] - 0.5) if x['claim'] in least else 1.0, x['claim'],
                                        abs((x['fit'] if x['fit'] is not None else 1.5) - 0.5)))


SECOND_LINE = 0.3  # confirmed filings under this fit get a second look, the least likely first (the tab's count too:
# on Oct 9 the list showed the 25 least likely whatever their fit, the tab counted those under the line, 3 against 25).
# 0.5 until Oct 12: the person kept 62% of first decisions at fits of 0.35-0.5, so a confirmed filing there was
# doubted on little more than a coin's say ("it doubts them as soon as i file them")
SECOND_WAIT = 30  # days: a filing the person confirmed this lately isn't doubted (a second look is for old slips)


def recently_confirmed(days: int = SECOND_WAIT) -> set[tuple[str, str]]:
    """(claim key, motif id) for every filing the person checked ✓ or not sure in the last `days`, from the curation log"""
    from app.analysis import curation_db, motif_index as mi
    since = (dt.now() - td(days=days)).isoformat(timespec='seconds')
    out = set()
    try:
        rows = curation_db.actions()
    except Exception:  # noqa: BLE001 - no log: nothing counts as recent
        return out
    for r in rows:
        if r['at'] < since:
            continue
        a = r['action']
        for step in (a.get('steps') or []) if a.get('action') == 'batch' else [a]:
            if isinstance(step, dict) and step.get('action') == 'check' and step.get('answer') in ('yes', 'unsure') \
                    and isinstance(step.get('claim'), str) and step.get('id'):
                out.add((mi.key(step['claim']), step['id']))
    return out


SURE_TALLY_DAYS = 7


def sure_tally(days: int = SURE_TALLY_DAYS, index: dict | None = None) -> list[dict]:
    """How the sure claims fared with the person, a day at a time, newest first: [{'day', 'clean', 'needed'}] (Oct 18,
    the person: "I feel like I'm having to heavily police the sure claims"; the held-out test said 95% right, but it
    counts only filings passed or taken out, and that day 9 of about 95 sure claims were held). A sure claim is clean
    when all of it passed; it needed the person when one of its sure filings was unticked, taken out, or the claim held.
    Holds logged before the ✅ sure tab marked its own count when all the claim's filings are sure now"""
    by = sure_tally_claims(days, index)
    return [{'day': d, 'clean': len(by[d]['clean']), 'needed': len(by[d]['needed'])} for d in sorted(by, reverse=True)]


def sure_tally_claims(days: int = SURE_TALLY_DAYS, index: dict | None = None) -> dict:
    """sure_tally's claims: {day: {'clean' and 'needed': {claim key: {'claim', 'ids': the sure filings' motifs}}}}
    (Baron Munchausen, F24, scores them again)"""
    from app.analysis import curation_db, motif_index as mi
    since = (dt.now() - td(days=days)).strftime('%Y-%m-%d')
    index = index if index is not None else mi.snapshot()
    least, waiting = {}, {}  # claim key -> its least fit now, over the filings still waiting; and those filings
    for e in mi.live(index):
        for c in e['claims']:
            if not c.get('checked') and c.get('fit') is not None:
                k = mi.key(c['claim'])
                least[k] = min(least.get(k, 1.0), c['fit'])
                waiting.setdefault(k, {'claim': c['claim'], 'ids': set()})['ids'].add(e['id'])
    clean, needed, now_sure = {}, {}, index_sure_at() or 1.0
    try:
        rows = curation_db.actions()
    except Exception:  # noqa: BLE001 - no log: no tally
        return {}

    def put(where, day, claim, eid=None):
        x = where.setdefault(day, {}).setdefault(mi.key(claim), {'claim': claim, 'ids': set()})
        if eid:
            x['ids'].add(eid)
    for r in rows:
        if r['at'] < since or r.get('by'):
            continue
        day, a, before = r['at'][:10], r['action'], r.get('before') or {}
        fits, sure_at = before.get('fits') or {}, before.get('sure_at')
        steps = (a.get('steps') or []) if a.get('action') == 'batch' else [a]
        for k in a.get('unticked') or []:
            claim, _, eid = k.rpartition('|')
            put(needed, day, claim, eid)
        for x in steps:
            if not isinstance(x, dict) or not isinstance(x.get('claim'), str):
                continue
            ck, fit = mi.key(x['claim']), fits.get(f"{mi.key(x['claim'])}|{x.get('id')}")
            sure = sure_at is not None and fit is not None and fit >= sure_at
            held_sure = x.get('action') == 'hold' and (x.get('from') == 'sure' or ('from' not in x and least.get(ck, 0) >= now_sure))
            if x.get('action') == 'check' and x.get('answer') == 'yes' and sure:
                put(clean, day, x['claim'], x['id'])
            elif x.get('action') == 'unfile' and sure:
                put(needed, day, x['claim'], x['id'])
            elif held_sure:
                put(needed, day, x['claim'])
                needed[day][ck]['ids'] |= waiting.get(ck, {}).get('ids', set())
    out = {}
    for day in set(clean) | set(needed):
        n = needed.get(day, {})
        out[day] = {'clean': {k: v for k, v in clean.get(day, {}).items() if k not in n}, 'needed': n}
    return out


PACE_DAYS = 14  # days the 📈 pace chart shows
PACE_STEADY_OVER = 7  # days whose arrivals set the pace that holds the queue steady


def pace(days: int = PACE_DAYS) -> dict:
    """The 📈 pace pop-up (Oct 18, the person: "how many am i at? ... a graph overview and how many to finish to hold
    steady"): a day at a time, the claims that arrived in the claims to judge (the filing's shortlist log: a claim
    filed in a motif for the first time) and the claims the person judged (their last word on any filing of it, through
    the checker or a slate applied on their word); how many wait now; and the day's target, the median arrivals of the
    last PACE_STEADY_OVER full days (median: the Oct 15 refile of 755 plain-news claims was a one-off)"""
    import statistics
    from app.analysis import filing_confidence as fc, motif_index as mi
    today = dt.now().strftime('%Y-%m-%d')
    since = (dt.now() - td(days=days - 1)).strftime('%Y-%m-%d')
    arrived, seen, first = {}, set(), None
    # only claims that reached the index or a decision of the person's: Rip Van Winkle's 687 practice filings of 1896
    # newspapers leaked into the log on Oct 15, before experiments had their own data, and showed as 755 arrivals
    real = set(mi.snapshot()['claims'])
    for r in fc.log_rows():
        if isinstance(r.get('action'), dict):
            d = {}
            fc._decided(r['action'], d)
            real.update(k for k, _ in d)
    try:
        with open(mi.SHORTLIST_LOG) as f:
            for line in f:
                r = json.loads(line)
                first = first or r['at'][:10]
                if (r.get('picked') or r.get('new')) and r['key'] not in seen and r['key'] in real:
                    seen.add(r['key'])
                    arrived[r['at'][:10]] = arrived.get(r['at'][:10], 0) + 1
    except (OSError, ValueError):
        pass
    judged = {}
    for r in fc.log_rows():
        if isinstance(r.get('action'), dict) and r['at'][:10] >= since:
            d = {}
            fc._decided(r['action'], d)
            judged.setdefault(r['at'][:10], set()).update(k for k, _ in d)
    out = []
    for n in range(days):
        day = (dt.now() - td(days=days - 1 - n)).strftime('%Y-%m-%d')
        out.append({'day': day, 'arrived': arrived.get(day, 0) if first and day >= first else None,
                    'judged': len(judged.get(day, ()))})
    full = [d['arrived'] for d in out if d['arrived'] is not None and d['day'] != today][-PACE_STEADY_OVER:]
    steady = round(statistics.median(full)) if full else None
    waiting = len(judge_queue())
    return {'days': out, 'today': out[-1]['judged'], 'steady': steady, 'waiting': waiting,
            'clear_in_14': steady + -(-waiting // 14) if steady is not None else None}


def code_version() -> str:
    """A fingerprint of the workbench's page code (its template, script and styles): an open tab that loaded another
    one shows a reload banner (Oct 19: a tab left open from the day before ran the old script all morning, so none of
    the day's fixes reached the person, and claims they had unticked came back)"""
    h = hashlib.sha1()
    for part in ('templates/workbench.html', 'static/workbench.js', 'static/workbench.css'):
        try:
            with open(os.path.join(CHECKER, part), 'rb') as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()[:12]


def index_sure_at() -> float | None:
    from app.analysis import filing_confidence as fc
    from app.utils.store import read_json
    return ((read_json(fc.MODEL, None) or {}).get('test') or {}).get('sure_at')


def doubted(e: dict, c: dict, hand: set, recent: set) -> bool:
    """A confirmed filing to look at again: the model finds it unlikely, and the person neither filed it by hand nor
    confirmed it lately, nor has looked again already"""
    from app.analysis import motif_index as mi
    k = (mi.key(c['claim']), e['id'])
    return ('done' in e and c.get('checked') == 'yes' and not c.get('rechecked') and c.get('fit') is not None
            and c['fit'] < SECOND_LINE and k not in hand and k not in recent)


def second_look() -> list[dict]:
    """The person's confirmed filings the confidence model finds least likely (an honest slip in 1,000 judgments
    teaches the models wrong): each to keep (✓ still fits, then off the list) or take out"""
    from app.analysis import motif_index as mi
    hand, recent = hand_made(), recently_confirmed()
    rows = [{'id': e['id'], 'name': e['name'], 'claim': c['claim'], 'source': c.get('source', ''), 'fit': c['fit']}
            for e in mi.live(mi.snapshot()) for c in e['claims'] if doubted(e, c, hand, recent)]
    rows = sorted(rows, key=lambda r: r['fit'])
    from app.analysis import filing_confidence as fc
    index = mi.snapshot()
    for r in rows:
        r['better'] = fc.better(index, r['claim'])  # where it might belong instead
    return rows


# Today's most useful decisions (Oct 8, the person: they can't confirm motifs eight hours a day): a short list that
# teaches the models most per minute of their time, not the whole queue. The filings the confidence model is torn on
# (nearest 50%: a decision there moves it most), the confirmed ones it now doubts with a better motif ready, the
# motifs the model made that nobody has shaped yet (their drafted note, genre and groups to keep or change), and the
# likeliest proposals for new motifs and groups.
TODAY = {'doubted': 0, 'torn': 0, 'new motifs': 10, 'proposals': 10}  # a day's set: since Oct 12 the motif-level decisions only
# (the torn and doubted filings are in the claims to judge, each claim whole: judge_queue)
TORN = (0.2, 0.8)  # a fit in this range: the model can't tell
TODAY_FILE = os.path.join(FOLDER, 'today.json')  # {'date', 'keys'}: the day's set, picked the first time it's asked for


def _today_candidates() -> dict[str, list[dict]]:
    """Every decision of each kind worth making now, the most useful first, each with its key"""
    from app.analysis import filing_confidence as fc, motif_index as mi, motif_proposals as mp
    index = mi.snapshot()
    live = mi.live(index)
    doubted = [{**r, 'kind': 'doubted', 'key': f"d|{r['claim']}|{r['id']}"} for r in second_look() if r.get('better')]
    torn, seen = [], set()
    for x in sorted(({'kind': 'torn', 'id': e['id'], 'name': e['name'], 'claim': c['claim'], 'source': c.get('source', ''),
                      'fit': c['fit']} for e in live if fc.yours(e) for c in e['claims']
                     if not c.get('checked') and c.get('fit') is not None and TORN[0] <= c['fit'] <= TORN[1]),
                    key=lambda x: abs(x['fit'] - 0.5)):
        if x['claim'] not in seen:  # one filing per claim: the most torn
            seen.add(x['claim'])
            torn.append({**x, 'key': f"t|{x['claim']}|{x['id']}", 'better': fc.better(index, x['claim'])})
    unshaped = sorted((e for e in live if e['claims'] and not e.get('curated') and 'done' not in e),
                      key=lambda e: -len(e['claims']))
    new = [{'kind': 'new motif', 'id': e['id'], 'name': e['name'], 'claims': len(e['claims']), 'key': f"n|{e['id']}"}
           for e in unshaped]
    first = {'new_motif': 0, 'new_group': 1}
    props = sorted(mp.open_proposals(), key=lambda p: (first.get(p['kind'], 2), -(p.get('fit') or 0)))
    proposals = [{'kind': 'proposal', 'proposal': {**p, 'do': mp.action(p)}, 'key': f"p|{p['id']}"} for p in props]
    return {'doubted': doubted, 'torn': torn, 'new motifs': new, 'proposals': proposals}


def _still(key: str, waiting: dict) -> dict | None:
    """A picked decision as it stands now, or None once it's made (the filing checked or gone, the motif done, the
    proposal decided)"""
    from app.analysis import filing_confidence as fc, motif_index as mi, motif_proposals as mp
    kind, rest = key.split('|', 1)
    if kind in ('t', 'd'):
        claim, eid = rest.rsplit('|', 1)
        e = mi.snapshot()['entries'].get(eid)
        c = next((c for c in (e or {}).get('claims', []) if c['claim'] == claim), None)
        if not c or (kind == 't' and c.get('checked')) or (kind == 'd' and (c.get('checked') != 'yes' or c.get('rechecked'))):
            return None
        return waiting.get(key) or {'kind': 'torn' if kind == 't' else 'doubted', 'id': eid, 'name': e['name'], 'claim': claim,
                                    'source': c.get('source', ''), 'fit': c.get('fit'), 'key': key,
                                    'better': fc.better(mi.snapshot(), claim)}
    if kind == 'n':
        e = mi.snapshot()['entries'].get(rest)
        return waiting.get(key) if e and not e.get('merged_into') and 'done' not in e and e.get('claims') else None
    if kind == 'p':
        return waiting.get(key) if any(p['id'] == rest for p in mp.open_proposals()) else None
    return None


def todays_decisions(more: bool = False) -> dict:
    """The day's set of the most useful decisions: picked the first time it's asked for each day (twenty: TODAY), kept
    for the day so it runs out as the person decides (it used to fill up again to twenty at every look); `more` adds
    another twenty. {'items': those still waiting, 'picked', 'done'}"""
    from datetime import date
    from app.utils.store import read_json, write_json
    today = date.today().isoformat()
    kept = read_json(TODAY_FILE, {})
    keys = kept.get('keys', []) if kept.get('date') == today else []
    pools = _today_candidates()
    waiting = {x['key']: x for pool in pools.values() for x in pool}
    if not keys or more:
        taken = set(keys)
        for kind, n in TODAY.items():
            keys += [x['key'] for x in pools[kind] if x['key'] not in taken][:n]
        write_json(TODAY_FILE, {'date': today, 'keys': keys})
    items = [x for x in (_still(k, waiting) for k in keys) if x]
    order = list(TODAY)
    items.sort(key=lambda x: order.index({'doubted': 'doubted', 'torn': 'torn', 'new motif': 'new motifs',
                                          'proposal': 'proposals'}[x['kind']]))
    return {'items': items, 'picked': len(keys), 'done': len(keys) - len(items)}


def hand_made() -> set:
    """(claim key, motif id) of the filings the person made themselves: the second look leaves them out (they score
    low because they're the structural links the model misses, not because they're slips; Oct 8)"""
    from app.analysis import filing_confidence as fc
    return {k for k, ok in fc.decisions(hand=True).items() if ok} - {k for k, ok in fc.decisions().items() if ok}


def judge_queue() -> list[dict]:
    """Every claim with a decision waiting, once each (Oct 12, the person: "I just seem to encounter the claims multiple
    times ... it's hard to judge a claim and its motifs holistically"; the check, unchecked, second look and today tabs
    each showed one filing of a claim at a time, so a claim in three motifs came up again and again). Each claim with
    why it's here: its filings nobody has checked (each with its fit), and its filings the person confirmed that the
    model now doubts (the second look). In the check queue's order (the least sure first: E6), the doubted after.
    Claims on hold (⏸, Oct 18) are left out"""
    out, by = [], {}

    def entry(x):
        if x['claim'] not in by:
            by[x['claim']] = {'claim': x['claim'], 'source': x.get('source', ''), 'reasons': [], 'fits': {}, 'unsure': [],
                              'better': []}
            out.append(by[x['claim']])
        return by[x['claim']]
    from app.analysis import motif_index as mi
    index = mi.snapshot()
    refiled = {(mi.key(c['claim']), e['id']): c['refiled'] for e in mi.live(index) for c in e['claims'] if c.get('refiled')}
    held = mi.held(index)  # ⏸ on hold: in the held tab, not here
    for x in check_queue():
        if mi.key(x['claim']) in held:
            continue
        e = entry(x)
        e['reasons'].append({'kind': 'unchecked', 'id': x['id'], 'fit': x.get('fit'),  # the watch list filed it again
                             **({'refiled': refiled[(mi.key(x['claim']), x['id'])]} if (mi.key(x['claim']), x['id']) in refiled else {})})
        if x.get('fit') is not None:
            e['fits'][x['id']] = x['fit']
        if not x.get('can_be_sure', True):
            e['unsure'].append(x['id'])
    for x in sorted(second_look(), key=lambda r: r['fit']):
        if mi.key(x['claim']) in held:
            continue
        e = entry(x)
        e['reasons'].append({'kind': 'doubted', 'id': x['id'], 'fit': x['fit']})
        e['fits'][x['id']] = x['fit']
        e['better'] = e['better'] or x.get('better') or []
    return out


def workbench_queue(kind: str):
    from app.analysis import motif_index as mi
    if kind == 'judge':
        return judge_queue()
    if kind == 'check':
        return check_queue()
    if kind == 'second':
        return second_look()
    if kind == 'today':
        return todays_decisions()
    if kind == 'today-more':
        return todays_decisions(more=True)
    if kind == 'singles':
        return mi.single_suggestions()
    if kind == 'pairs':
        try:
            similar, note = [{'a': a, 'b': b, 'score': round(sim, 2)} for a, b, sim in mi.suggestions(40)], None
        except Exception as e:  # noqa: BLE001 - the embeddings need Ollama
            similar, note = [], f'similar names unavailable: {type(e).__name__}'
        return {'similar': similar, 'shared': mi.shared_pairs(), 'note': note}
    if kind == 'held':  # ⏸ the claims on hold, the latest held first, with how many filings still wait on each
        index = mi.snapshot()
        held, waiting = mi.held(index), {}
        for e in mi.live(index):
            for c in e['claims']:
                k = mi.key(c['claim'])
                if k in held:
                    x = waiting.setdefault(k, {'claim': c['claim'], 'at': held[k]['at'], 'waiting': set()})
                    if not c.get('checked'):  # motifs, not records: a claim told by two sources is two records
                        x['waiting'].add(e['id'])
        return sorted(({**x, 'waiting': len(x['waiting'])} for x in waiting.values()), key=lambda x: x['at'], reverse=True)
    if kind == 'tellings':  # 🧩 Pandora's tellings of the flabby motifs, still to decide
        from app.analysis import tellings
        return tellings.drafted()
    if kind == 'splits':  # the claim organizer's open splits, with each child's posts
        from app.analysis import claim_organizer as co
        return co.open_splits()
    if kind == 'proposals':  # the correction proposer's open proposals, each with the action that carries it out
        from app.analysis import motif_proposals as mp
        return [{**p, 'do': mp.action(p)} for p in mp.open_proposals()]
    raise ValueError(f'no such queue: {kind}')


def record_check(data: dict):
    os.makedirs(FOLDER, exist_ok=True)
    with open(MOTIF_VERDICTS, 'a') as f:
        f.write(json.dumps({'claim': data['claim'], 'id': data['id'], 'answer': data['answer'],
                            'at': dt.now().isoformat(timespec='seconds')}) + '\n')


def critique(data: dict) -> dict:
    """The person's words on what was wrong with a proposal they decided, kept on the proposal and in the curation log:
    the model's draft, the critique and the final version together, examples for the proposer and the namer, and the
    trail of the person's authorship (Fable, Oct 12)"""
    from app.analysis import motif_proposals as mp
    why = data.get('why')
    if not isinstance(why, str) or not why.strip() or not isinstance(data.get('proposal'), str):
        raise ValueError('a critique needs a proposal and what was wrong')
    p = mp.critique(data['proposal'], why)
    log_curation('/critique', {'action': 'critique', 'proposal': p['id'], 'why': p['why']},
                 {'proposal': {k: p.get(k) for k in ('kind', 'args', 'reason', 'status')}})
    return {'ok': True}


def workbench_action(data: dict):
    """One action (motif_actions.py), the person's checks recorded for agreement scores"""
    from app.analysis import motif_actions
    motif_actions.apply(data, on_check=record_check)


def entities_state() -> dict:
    """The names organizer's data (#165): suggested merges (a name inside another, the first 40, each with both
    subjects' story counts), every subject with its story count and the other names that point to it (most stories
    first), and how many names there are. The old page renders it; the React app reads it as /entities.json."""
    from app.analysis import entities
    book = entities.load_aliases()
    counts = entities.all_names()
    subjects = {}
    for n, c in counts.items():
        name = entities.canonical(n, book['aliases'])
        entry = subjects.setdefault(name, {'stories': 0, 'names': set()})
        entry['stories'] += c
        if n != name:
            entry['names'].add(n)
    for alias, name in book['aliases'].items():  # aliases a person made, even before any story uses them
        if alias != name.lower() and name in subjects:
            subjects[name]['names'].add(alias)
    stories_of = lambda name: subjects.get(name, {}).get('stories', 0)  # noqa: E731
    return {'pairs': [{'a': a, 'b': b, 'a_stories': stories_of(a), 'b_stories': stories_of(b)}
                      for a, b in entities.suggestions()[:40]],
            'name_count': len(counts),
            'subjects': [{'name': name, 'stories': e['stories'], 'names': sorted(e['names'])}
                         for name, e in sorted(subjects.items(), key=lambda kv: (-kv[1]['stories'], kv[0].lower()))]}


def entities_page() -> str:
    """The names organizer's old page, from entities_state()"""
    s = entities_state()
    return render('names.html', '/entities', pairs=[(p['a'], p['b']) for p in s['pairs']], name_count=s['name_count'],
                  subjects=[(e['name'], e) for e in s['subjects']],
                  stories_of=lambda name: next((e['stories'] for e in s['subjects'] if e['name'] == name), 0))


def entities_action(data: dict):
    """Apply one names-organizer action; raises on anything unknown or missing."""
    from app.analysis import entities
    act = data.get('action')
    text = lambda k: isinstance(data.get(k), str) and data[k].strip()  # noqa: E731
    if act == 'merge' and text('source') and text('target'):
        entities.merge(data['source'].strip(), data['target'].strip())
    elif act == 'not_same' and text('a') and text('b'):
        entities.not_same(data['a'], data['b'])
    elif act == 'unmerge' and text('name'):
        entities.unmerge(data['name'].strip())
    else:
        raise ValueError(f'unknown action: {data}')


class NotFound(Exception):
    pass


def _claims(q: dict):
    from app.analysis import motif_index
    words = q.get('q', '').lower().split()
    found = [c for c in motif_index.searchable_claims() if all(w in c['claim'].lower() for w in words)]
    return sorted(found, key=lambda c: (bool(c['motifs']), c['claim']))[:60]


def _better(q: dict):  # where a weakly filed claim might belong instead
    from app.analysis import filing_confidence as fc, motif_index
    return fc.better(motif_index.snapshot(), q.get('claim', ''))


def _motif_similar(q: dict):
    from app.analysis import motif_index
    eid = q.get('id', '')
    if eid not in {e['id'] for e in motif_index.live(motif_index.snapshot())}:
        raise NotFound(f'no such motif: {eid}')
    return motif_index.similar(eid)


def _claim_similar(q: dict):
    from app.analysis import motif_index
    return motif_index.similar_claims(q.get('claim', ''))


def _live(q: dict):  # 🧠 the filing pipeline as it runs (app/analysis/trace_view.py)
    from app.analysis import trace_view
    return trace_view.view(q)


def _flow(q: dict):  # 🌊 news stories into retellings over time (app/analysis/flow.py)
    from app.analysis import flow
    return flow.flow()


def _dashboard(q: dict):  # 📈 everything at a glance (app/dashboard.py)
    from app import dashboard
    return dashboard.gather(fresh=q.get('fresh') == '1')


def _workbench_metrics(q: dict):
    from app import health
    from app.analysis import motif_index
    from app.utils.store import read_json
    return {**motif_index.metrics_history(), 'health': read_json(health.HEALTH, None)}


def _workbench_queue(q: dict):
    try:
        return workbench_queue(q.get('kind', ''))
    except ValueError as e:
        raise NotFound(str(e)) from e


def _claim_map(q: dict):  # the map's 🧲 claims mode
    from app.analysis import claim_map
    return claim_map.cached()


def _board(q: dict):
    from app.analysis import motif_index
    return motif_index.board()


def _checkpoints(q: dict):
    from app.analysis import curation_db
    return curation_db.checkpoints()


def _undo_next(q: dict):
    found = last_undo()
    return {'what': found[1]['what'] if found else None}


# The data each page reads: path -> its JSON, from the query string's values. 🧪 the experiments page's three come from
# scripts/experiments/lab.py
GET_JSON = {
    '/workbench.json': lambda q: workbench_state(),
    '/workbench-queue.json': _workbench_queue,
    '/workbench-metrics.json': _workbench_metrics,
    '/motif-board.json': _board,
    '/motif-claim-map.json': _claim_map,
    '/claims.json': _claims,
    '/claim-detail.json': lambda q: claim_detail(q.get('claim', '')),
    '/better.json': _better,
    '/motif-similar.json': _motif_similar,
    '/claim-similar.json': _claim_similar,
    '/checkpoints.json': _checkpoints,
    '/undo.json': _undo_next,
    '/version.json': lambda q: {'version': code_version()},  # the workbench's own code now: an open tab compares
    '/pace.json': lambda q: pace(),  # 📈 the person's pace against what arrives
    '/live.json': _live,
    '/flow.json': _flow,
    '/dashboard.json': _dashboard,
    '/experiments.json': lambda q: experiments_lab().overview(),
    '/experiment-paper.json': lambda q: experiments_lab().paper(q.get('code', '')),
    '/experiment-cases.json': lambda q: experiments_lab().cases(q.get('code', '')),
    '/entities.json': lambda q: entities_state(),  # 👥 the names organizer
    '/labels.json': lambda q: labels.state(),  # 🏷️ a fresh batch for the label check, with the running agreement
}


def query(path: str) -> dict:
    from urllib.parse import parse_qs, urlparse
    return {k: v[0] for k, v in parse_qs(urlparse(path).query).items()}


UI = os.path.join(CHECKER, 'ui', 'dist')  # the checker's React app (scripts/checker/ui), built; served at /ui/ (Oct 21)
UI_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8',
            '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json',
            '.woff2': 'font/woff2', '.map': 'application/json'}


def ui_file(path: str) -> tuple[str, bool] | None:
    """The built app's file for a /ui/ path, and whether it may be cached for good (its name carries its hash); any
    other path under /ui/ is the app's own page (index.html), which routes it"""
    rel = path[len('/ui'):].lstrip('/')
    if rel.startswith('assets/'):
        file = os.path.realpath(os.path.join(UI, rel))
        if file.startswith(os.path.realpath(UI) + os.sep) and os.path.isfile(file):
            return file, True
        return None
    index = os.path.join(UI, 'index.html')
    return (index, False) if os.path.isfile(index) else None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/ui' or path.startswith('/ui/'):
            found = ui_file(path)
            if not found:
                self.send_error(404)
                return
            file, forever = found
            with open(file, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', UI_TYPES.get(os.path.splitext(file)[1], 'application/octet-stream'))
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if forever else 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in GET_JSON:
            try:
                return self.send_json(GET_JSON[path](query(self.path)))
            except NotFound as e:
                return self.send_json_error(404, str(e))
        if path == '/motif-export':  # ?format=json|csv|md|ttl&scope=verified|all, as a download
            from app.analysis import motif_export
            q = query(self.path)
            fmt, scope = q.get('format', 'json'), q.get('scope', 'verified')
            if fmt not in motif_export.FORMATS or scope not in motif_export.SCOPES:
                return self.send_json_error(400, f'format: {sorted(motif_export.FORMATS)}; scope: {motif_export.SCOPES}')
            text, media, name = motif_export.export(fmt, scope)
            body = text.encode()
            self.send_response(200)
            self.send_header('Content-Type', f'{media}; charset=utf-8')
            self.send_header('Content-Disposition', f'attachment; filename="{name}"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith('/checker/static/'):
            name = os.path.basename(path)
            file = SHARED_STATIC.get(name) or os.path.join(CHECKER, 'static', name)
            if os.path.splitext(name)[1] not in STATIC_TYPES or not os.path.isfile(file):
                self.send_error(404)
                return
            with open(file, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', STATIC_TYPES[os.path.splitext(name)[1]])
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        page_of = next((f for prefix, f in STATIC_PAGES.items() if path.startswith(prefix)), None)
        if path.startswith(('/motif-index', '/motif-singles')) or path == '/motif-board':  # dropped pages: to the workbench
            self.send_response(302)
            self.send_header('Location', '/motif-workbench')
            self.end_headers()
            return
        body = (render(page_of, path, undo=page_of not in ('dashboard.html', 'experiments.html', 'flow.html', 'live.html')) if page_of else motif_page() if path.startswith('/motifs') else entities_page() if path.startswith('/entities')
                else labels.page(render))
        body = body.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')  # a page changed under an open tab shows on reload, never stale
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def remember(self, data: dict, before: dict, by: str | None = None, proposals: list[str] | None = None):
        if getattr(self, '_undo', None):
            push_undo(self._undo[0], self._undo[1], describe(data, before) + (f' (by {by.capitalize()})' if by else ''),
                      proposals)

    def send_json(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json_error(self, code: int, message: str):
        body = json.dumps({'error': message[:300]}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/experiment-verdict':  # the person's verdict on an experiment's item (Pandora's tellings)
            try:
                return self.send_json(experiments_lab().verdict(data.get('code', ''), data.get('key', ''), data.get('verdict')))
            except (ValueError, OSError) as e:
                return self.send_json_error(400, str(e))
        if self.path == '/critique':  # what the person said was wrong with a proposal, after deciding it (not undone)
            try:
                return self.send_json(critique(data))
            except (ValueError, OSError) as e:
                return self.send_json_error(400, str(e))
        if self.path == '/undo':
            try:
                what = undo()
            except ValueError as e:
                self.send_error(409, str(e)[:300])
                return
            return self.send_json({'undid': what})
        if self.path == '/checkpoint':  # save the state by name, or go back to a saved one
            try:
                if data.get('action') == 'go back':
                    done = go_back(int(data['id']))
                    return self.send_json({'went_back': done, 'state': workbench_state()})
                return self.send_json({'saved': save_checkpoint(str(data.get('name') or '').strip() or 'saved state')})
            except (ValueError, KeyError) as e:
                return self.send_json_error(400, str(e))
        undo_path = undo_paths().get(self.path)
        self._undo = (undo_path, state(undo_path)) if undo_path else None
        if self.path == '/workbench':
            by = data.pop('by', None)  # an action someone else made at the person's request (claude, by MCP)
            by = by if by in BY else None
            try:
                before = motif_context(data if data.get('action') != 'batch' else (data.get('steps') or [{}])[0])
                if data.get('action') == 'batch':  # each step's own context too: a draft renamed in step 5 is known
                    before['steps'] = [motif_context(x) if isinstance(x, dict) else {} for x in data.get('steps') or []]
                before.update(decision_fits(data))
                workbench_action(data)
                log_curation('motif workbench', data, before, by)
                steps = data['steps'] if data.get('action') == 'batch' else [data]
                self.remember(data if data.get('action') != 'batch' else
                              {'action': f"{len(data['steps'])} changes: {data['steps'][0].get('action')}…"}, before, by,
                              [x['proposal'] for x in steps if isinstance(x, dict) and x.get('proposal')])
            except (ValueError, KeyError) as e:
                if getattr(e, 'done', None):  # a batch stopped midway: what it did is logged, and still undoable
                    log_curation('motif workbench', {'action': 'batch', 'steps': e.done}, before, by)
                self.remember({'action': 'part of a change that failed'}, {}, by)
                return self.send_json_error(400, str(e))
            return self.send_json(workbench_state())
        if self.path == '/motif-board':
            from app.analysis import motif_index
            try:
                before = motif_context(data)
                before.update(decision_fits(data))
                board_action(data)
                log_curation('motif board', data, before)
                self.remember(data, before)
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e)[:200])
                return
            return self.send_json(motif_index.board())
        if self.path == '/entities':
            try:
                from app.analysis import entities
                before = {'aliases': {k: v for k, v in entities.load_aliases()['aliases'].items()
                                      if any(isinstance(x, str) and x.lower() in (k, v.lower()) for x in data.values())}}
                entities_action(data)
                log_curation('names', data, before)
                self.remember(data, {})
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e)[:200])
                return
            self.send_response(204)
            self.end_headers()
            return
        if self.path == '/motif-verdict':  # the ✅ check page: a check, recorded like the workbench's
            data['action'] = 'check'
            try:
                before = motif_context(data)
                before.update(decision_fits(data))
                workbench_action(data)
                log_curation('motif check', data, before)
                self.remember(data, before)
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e)[:200])
                return
            self.send_response(204)
            self.end_headers()
            return
        if self.path != '/verdict':
            self.send_error(404)
            return
        if not isinstance(data.get('headline_id'), int):
            self.send_error(400)
            return
        try:
            labels.record(data)  # straight onto the headline; the file keeps the record for agreement scores
        except (ValueError, KeyError) as e:
            self.send_error(400, str(e)[:200])
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def follow_code(server, every: int = 60):
    """As a service (deploy/systemd/maudlin-checker.service): once its checkout has new code (the hourly run pulls),
    stop serving, so systemd starts it again on the new code a moment later"""
    import subprocess
    import threading
    import time
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def head():
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True).stdout.strip()
    start = head()

    def watch():
        while True:
            time.sleep(every)
            if head() != start:
                print('New code: stopping, to be started again on it', flush=True)
                server.shutdown()
                return
    threading.Thread(target=watch, daemon=True).start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--follow-code', action='store_true', help='stop once the checkout has new code (the service)')
    args = parser.parse_args()
    print(f'Label check on http://0.0.0.0:{args.port} (Ctrl-C to stop)')
    server = ThreadingHTTPServer(('0.0.0.0', args.port), Handler)
    if args.follow_code:
        follow_code(server)
    server.serve_forever()
