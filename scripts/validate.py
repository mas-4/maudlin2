"""Check the language model's headline labels by eye (#121): a small local page, never part of the site or deployed.

Run it, open http://<this machine>:8766 on any device on the network, and for each headline mark the model's mood,
spice (loaded wording) and feelings right, or pick what they should be. Verdicts are appended to
data/validation/verdicts.jsonl (one line per headline, with the model's labels at the time), and the page's footer
keeps a running agreement count. Headlines are drawn from the last two days, spread evenly over the model's mood and
spice values so the rare ones (very grim, very loaded) get checked as often as the common ones.

    .venv/bin/python scripts/validate.py [--port 8766]
"""
import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime as dt, timedelta as td
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI  # noqa: E402
from app.models import Session, Headline, Article, Agency  # noqa: E402
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
       ('/motifs', '✅ check', 'motifs'), ('/motif-empty', '🫙 empty', 'motifs'),
       ('/motif-notes', '📝 notes', 'motifs'),
       ('/', '🏷️ label check', 'other'), ('/entities', '👥 names', 'other')]
_templates = None


def render(template: str, here: str, undo: bool = True, **context) -> str:
    """A checker page from its template: `here` is its path in the nav; `undo` adds the undo button (every
    organizer page; the label check writes the database instead)."""
    global _templates
    if _templates is None:
        from jinja2 import Environment, FileSystemLoader
        _templates = Environment(loader=FileSystemLoader(os.path.join(CHECKER, 'templates')), autoescape=True)
    return _templates.get_template(template).render(nav=NAV, here=here, undo=undo, **context)


STATIC_PAGES = {'/motif-workbench': 'workbench.html', '/motif-map': 'map.html', '/motif-empty': 'empty.html',
                '/motif-notes': 'notes.html'}
STATIC_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}


FOLDER = os.path.join(Config.data, 'validation')
VERDICTS = os.path.join(FOLDER, 'verdicts.jsonl')
BATCH = 12
MOODS = {-2: ('⛈️', 'grim+'), -1: ('🌧️', 'grim'), 0: ('🍞', 'plain'), 1: ('🌤️', 'upbeat'), 2: ('☀️', 'upbeat+')}
SPICES = {0: ('🍞', 'plain'), 1: ('🌶️', 'loaded'), 2: ('🌶️🌶️', 'loaded+')}
FEELINGS = [e for e in EMOTIONS if e != 'neutral']


def judged() -> list[dict]:
    try:
        with open(VERDICTS) as f:
            return [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []


def batch(n: int = BATCH) -> list[dict]:
    """Headlines not yet judged, from the last two days, spread over the model's mood and spice values."""
    done = {v['headline_id'] for v in judged()}
    since = dt.utcnow() - td(days=2)
    with Session() as s:
        rows = s.query(Headline.id, Headline.processed, Agency.name, Headline.event_score, Headline.loaded_score,
                       Headline.emotion_ranks, Article.url).join(Headline.article).join(Article.agency).filter(
            Headline.first_accessed > since, Headline.event_score.isnot(None), Headline.loaded_score.isnot(None),
        ).all()
    pool = {}
    for hid, title, agency, mood, loaded, ranks, url in rows:
        if hid in done or not title:
            continue
        item = {'headline_id': hid, 'title': title.strip(), 'agency': agency, 'mood': int(mood),
                'spice': int(loaded), 'feelings': [e for e in (ranks or '').split(',') if e in FEELINGS][:3],
                'url': url}
        pool.setdefault((item['mood'], item['spice']), []).append(item)
    rng = random.Random()
    cells = list(pool)
    rng.shuffle(cells)
    out = []
    while len(out) < n and any(pool.values()):
        for cell in cells:
            if pool[cell] and len(out) < n:
                out.append(pool[cell].pop(rng.randrange(len(pool[cell]))))
    return out


def apply_label(data: dict):
    """A checked headline's labels become hand labels, on the headline itself: the corrected mood, spice and feelings
    where the model was wrong, its own where it was right; marked so no rescore replaces them."""
    from app.analysis.newsfilter import HAND_JUDGE, ranked
    model = data.get('model') or {}
    pick = lambda m: model.get(m) if (data.get(m) or {}).get('ok') else (data.get(m) or {}).get('should')  # noqa: E731
    mood, spice, feelings = pick('mood'), pick('spice'), pick('feelings')
    if not isinstance(mood, int) or not isinstance(spice, int) or not isinstance(feelings, list):
        raise ValueError('a verdict needs mood, spice and feelings')
    # The model's order for feelings it also had, then the ones added
    feelings = [e for e in model.get('feelings', []) if e in feelings] + [e for e in feelings if e not in model.get('feelings', [])]
    with Session() as s:
        h = s.get(Headline, data['headline_id'])
        if h is None:
            raise ValueError('no such headline')
        h.event_score, h.loaded_score = float(mood), float(spice)
        for k, v in ranked(feelings).items():
            setattr(h, k, v)
        h.scored_by, h.scored_at = HAND_JUDGE, dt.utcnow()
        s.commit()


def stats() -> dict:
    rows = judged()
    out = {'headlines': len(rows)}
    for measure in ('mood', 'spice', 'feelings'):
        marks = [r[measure]['ok'] for r in rows if measure in r]
        out[measure] = (sum(marks), len(marks))
    off = Counter((r['model']['mood'], r['mood'].get('should')) for r in rows if not r.get('mood', {}).get('ok', True))
    out['mood_misses'] = off.most_common(3)
    return out


def page() -> str:
    items = batch()
    st = stats()
    for it in items:
        it['model_json'] = json.dumps({k: it[k] for k in ('mood', 'spice', 'feelings')})
    pct = lambda k: f"{100 * st[k][0] / st[k][1]:.0f}% of {st[k][1]}" if st[k][1] else '—'  # noqa: E731
    return render('label.html', '/', undo=False, items=items, st=st, pct=pct, moods=MOODS, spices=SPICES,
                  feelings=FEELINGS, emoji=EMOTION_EMOJI)


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
    index = mi.load()
    entries = index['entries']

    def motif(eid):
        e = entries.get(eid)
        return e and {'id': eid, 'name': e['name'], 'by': 'person' if e.get('curated') else 'model',
                      'claims': [c['claim'] for c in e['claims'][:8]], 'size': len(e['claims'])}
    out = {k: motif(data[k]) for k in ('id', 'source', 'target', 'a', 'b', 'child', 'parent') if isinstance(data.get(k), str) and data[k] in entries}
    claim = data.get('claim')
    if isinstance(claim, str) and claim:
        out['claim_motifs'] = [motif(i) | {'claims': None} for i in mi._ids(index, mi.key(claim)) if i in entries]
    return out


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
    return {'/motif-board': motif_index.INDEX, '/motif-index': motif_index.INDEX, '/motif-verdict': motif_index.INDEX,
            '/workbench': motif_index.INDEX,
            '/entities': entities.ALIASES}


def read_text(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


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
    after = read_text(path)
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
        now = read_text(snap['path']) or ''
        if hashlib.sha1(now.encode()).hexdigest() != snap['after_sha']:
            raise ValueError('the index has changed since that edit (an hourly run filing claims?), so undoing it '
                             'would lose those changes: fix it by hand instead')
        with open(snap['path'] + '.tmp', 'w') as f:
            f.write(snap['before'] or '')
        os.replace(snap['path'] + '.tmp', snap['path'])
    os.remove(snap_path)
    if snap.get('proposals'):
        from app.analysis import motif_proposals
        motif_proposals.reopen(snap['proposals'])
    log_curation('undo', {'action': 'undo', 'undid': snap['what']}, {})
    return snap['what']


def show_tellings(words: set[str]) -> list[dict]:
    """Every telling of a claim retold across the shows (show_claims.kept_retold, the group whose claim is one of
    `words`): the show, its lean, the episode, who said it, about when, the quote and the transcript around it"""
    from app.analysis import focus_group, show_claims
    group = next((r for r in show_claims.kept_retold() if r['claim'] in words), None)
    if group is None:  # not in the last run's groups: its own episode's claims, at least
        group = {'told': [dict(c, show=e['show'], url=url) for url, e in show_claims.load().items()
                          for c in e.get('claims', []) if c['claim'] in words]}
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
        return curation_db.checkpoint(name, read_text(mi.INDEX) or '{}', read_text(mp.PROPOSALS), kind)


def go_back(cid: int) -> dict:
    """The motif index and proposals put back as checkpoint `cid` saved them. What's there now is saved first (a
    checkpoint 'before going back'), so this can itself be gone back on, and it's one undo step too; the changes since
    the checkpoint stay in the log, marked reverted, so the models stop learning from them"""
    from app.analysis import curation_db, motif_index as mi, motif_proposals as mp
    from app.utils.store import write_json
    cp, index_text, proposals_text = curation_db.restore(cid)
    with mi.locked():
        now_index, now_proposals = read_text(mi.INDEX), read_text(mp.PROPOSALS)
        before = curation_db.checkpoint(f'before going back to “{cp["name"]}”', now_index or '{}', now_proposals,
                                        kind='before going back')
        mi.save(json.loads(index_text))
        if proposals_text is not None:
            write_json(mp.PROPOSALS, json.loads(proposals_text))
    undone = curation_db.set_reverted(cp)
    push_undo(mi.INDEX, now_index, f'go back to “{cp["name"]}”')
    log_curation('checkpoints', {'action': 'go back', 'to': cid, 'name': cp['name'], 'reverted': undone,
                                 'saved_first': before['id']}, {})
    return {'to': cp, 'reverted': undone, 'saved_first': before}


def claim_detail(claim: str) -> dict:
    """What's behind a claim for the motif board: the fact-check it came from (headline, summary, link, the model's
    labels) or the folklore group (how many told it, a few of their posts, linked articles, labels). Local only."""
    from app.analysis import factchecks, motif_index as mi
    index = mi.load()
    words = mi.originals(claim, index)
    filed = next((c for e in mi.live(index) for c in e['claims'] if c['claim'] == claim), {})
    out = {'claim': claim, 'source': filed.get('source', ''), 'model_words': sorted(words - {claim})}
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
        out.update(kind='fact-check', url=url, title=item.get('title'), summary=item.get('summary'),
                   published=(item.get('published') or '')[:10], label=label)
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
    """One change from the motif board, applied to the index at once (under its lock)."""
    from app.analysis import motif_index as mi
    index = mi.load()
    live = {e['id'] for e in mi.live(index)}
    text = lambda k: isinstance(data.get(k), str) and data[k].strip()  # noqa: E731
    act = data.get('action')
    if act == 'move' and text('claim') and data.get('source') in live and data.get('target') in live:
        mi.move(data['claim'], data['source'], data['target'])
    elif act == 'also' and text('claim') and data.get('source') in live and data.get('target') in live:
        mi.also_file(data['claim'], data['source'], data['target'])
    elif act == 'also_new' and text('claim') and data.get('source') in live and text('name'):
        mi.also_file(data['claim'], data['source'], mi.add(data['name']))
    elif act == 'move_new' and text('claim') and data.get('source') in live and text('name'):
        mi.move(data['claim'], data['source'], mi.add(data['name']))
    elif act == 'unfile' and text('claim') and data.get('id') in live:
        mi.unfile(data['claim'], data['id'])
    elif act == 'no_motif' and text('claim'):
        mi.no_motif(data['claim'])
    elif act in ('relate', 'unrelate') and data.get('a') in live and data.get('b') in live:
        mi.relate(data['a'], data['b'], act == 'relate')
    elif act == 'parent' and data.get('id') in live and data.get('parent') in live:
        mi.set_parent(data['id'], data['parent'], data.get('on', True) is not False)
    elif act == 'file' and text('claim') and data.get('id') in live:
        mi.file_by_hand({'claim': data['claim'].strip(), 'source': data.get('source', ''), 'ref': data.get('ref', '')}, data['id'])
    elif act == 'note' and data.get('id') in live and isinstance(data.get('note'), str):
        mi.set_note(data['id'], data['note'])
    elif act == 'keep_note' and data.get('id') in live:
        mi.keep_note(data['id'])
    elif act == 'stands_alone' and data.get('id') in live:
        mi.stands_alone(data['id'], data.get('alone', True) is not False)
    elif act == 'correct' and text('claim') and text('text'):
        mi.correct_claim(data['claim'], data['text'])
    elif act == 'reject' and text('claim') and data.get('id') in live:
        mi.reject(data['claim'], data['id'])
    elif act == 'done' and data.get('id') in live:
        mi.mark_done(data['id'], bool(data.get('done', True)))
    elif act == 'reset_done':
        mi.reset_done()
    elif act == 'group_add' and text('name'):
        mi.group_add(data['name'])
    elif act == 'group_new' and text('name'):  # a new group, with a first motif in it if one is given (one undo step)
        gid = mi.group_add(data['name'])
        if data.get('id') in live:
            mi.group_member(data['id'], gid)
    elif act == 'group_rename' and data.get('group') in index.get('groups', {}) and text('name'):
        mi.group_rename(data['group'], data['name'])
    elif act == 'group_delete' and data.get('group') in index.get('groups', {}):
        mi.group_delete(data['group'])
    elif act == 'group_assign' and data.get('id') in live:
        mi.group_assign(data['id'], data.get('group') or None)
    elif act == 'group_member' and data.get('id') in live and data.get('group') in index.get('groups', {}):
        mi.group_member(data['id'], data['group'], data.get('on', True) is not False)
    elif act in ('rename', 'merge', 'delete', 'add'):
        organizer_action(data)
    else:
        raise ValueError(f'unknown action: {data}')


# The motif workbench (workbench.html): one page for everything the motif pages do. Its state is the board's plus
# what only other pages had (stands alone, checks to do); its actions are the board's plus 'not the same', the motif
# check, and a batch of several (one undo step for a whole multi-select drag)
def workbench_state() -> dict:
    from app.analysis import motif_index as mi
    index = mi.load()
    state = mi.board()
    for e in state['entries']:
        entry = index['entries'].get(e['id'], {})
        e['stands_alone'] = bool(entry.get('stands_alone'))
        e['phrases'] = (entry.get('phrases') or [])[:6]
    state['to_check'] = sum(1 for e in mi.live(index) for c in e['claims'] if not c.get('checked'))
    state['not_same'] = [sorted(p) for p in index.get('not_same', [])]
    state['facets'] = mi.facet_values(index)
    from app.analysis import motif_proposals as mp
    state['proposals'] = len(mp.open_proposals())  # the 💡 tab's count
    from app.analysis import filing_confidence as fc
    from app.utils.store import read_json
    m = read_json(fc.MODEL, None)  # how sure 'sure' is, as tested held out
    sure = m and m['test'].get('sure_at')
    state['confidence'] = {'sure_at': sure, 'auc': m['test']['auc'],
                           'at_sure': next((t for t in m['test']['thresholds'] if t['at'] == sure), None)} if sure else None
    return state


def filing_fits() -> dict:
    """Each unchecked filing's fit, as the hourly run left it on the filing (filing_confidence.refresh: the checker
    never asks the models itself)"""
    from app.analysis import motif_index as mi
    return {f"{mi.key(c['claim'])}|{e['id']}": c['fit'] for e in mi.live(mi.load()) for c in e['claims']
            if not c.get('checked') and c.get('fit') is not None}


def check_queue() -> list[dict]:
    """Every filing nobody has checked, each with its fit (the chance the person keeps it; only in their own motifs),
    the claims whose least likely filing is likeliest first, so the sure ones come first and the doubtful ones last"""
    from app.analysis import filing_confidence as fc, motif_index as mi
    items = mi.to_check()
    fits = filing_fits()
    index = mi.load()
    tested = fc.tested_sources(index) if fits else set()
    for x in items:
        x['fit'] = fits.get(f"{mi.key(x['claim'])}|{x['id']}")
        x['can_be_sure'] = fc.can_be_sure(index, x['claim'], x['id'], x.get('source', ''), tested)
    if not fits:
        return items[:40]  # the old order: biggest motifs first
    # a claim's place: its least likely filing in your motifs; one only in the model's own motifs (no fit) goes last
    least = {}
    for x in items:
        if x['fit'] is not None:
            least[x['claim']] = min(least.get(x['claim'], 1.0), x['fit'])
    return sorted(items, key=lambda x: (-least.get(x['claim'], -1.0), x['claim'], -(x['fit'] or 0)))


def workbench_queue(kind: str):
    from app.analysis import motif_index as mi
    if kind == 'check':
        return check_queue()
    if kind == 'singles':
        return mi.single_suggestions()
    if kind == 'pairs':
        try:
            similar, note = [{'a': a, 'b': b, 'score': round(sim, 2)} for a, b, sim in mi.suggestions(40)], None
        except Exception as e:  # noqa: BLE001 - the embeddings need Ollama
            similar, note = [], f'similar names unavailable: {type(e).__name__}'
        return {'similar': similar, 'shared': mi.shared_pairs(), 'note': note}
    if kind == 'proposals':  # the correction proposer's open proposals, each with the action that carries it out
        from app.analysis import motif_proposals as mp
        return [{**p, 'do': mp.action(p)} for p in mp.open_proposals()]
    raise ValueError(f'no such queue: {kind}')


def record_check(data: dict):
    os.makedirs(FOLDER, exist_ok=True)
    with open(MOTIF_VERDICTS, 'a') as f:
        f.write(json.dumps({'claim': data['claim'], 'id': data['id'], 'answer': data['answer'],
                            'at': dt.now().isoformat(timespec='seconds')}) + '\n')


def workbench_action(data: dict):
    from app.analysis import motif_index as mi
    act = data.get('action')
    if data.get('proposal'):  # a proposal approved (its own action, carried out as usual) or rejected
        from app.analysis import motif_proposals as mp
        if act != 'proposal_reject':
            workbench_action({k: v for k, v in data.items() if k != 'proposal'})
        mp.decide(data['proposal'], 'rejected' if act == 'proposal_reject' else 'approved')
        return
    if act == 'batch':
        steps = data.get('steps')
        if not isinstance(steps, list) or not steps or any(not isinstance(x, dict) or x.get('action') == 'batch' for x in steps):
            raise ValueError('a batch is a list of actions')
        for step in steps:
            workbench_action(step)
    elif act == 'not_same':
        live = {e['id'] for e in mi.live(mi.load())}
        if data.get('a') not in live or data.get('b') not in live or data['a'] == data['b']:
            raise ValueError('not the same: two motifs')
        mi.not_same(data['a'], data['b'])
    elif act == 'check':
        if data.get('answer') not in ('yes', 'no', 'unsure'):
            raise ValueError('a check is yes, no or unsure')
        mi.check(data.get('claim', ''), data.get('id', ''), data['answer'])
        record_check(data)
    elif act == 'facet':  # a motif's genre (or none)
        live = {e['id'] for e in mi.live(mi.load())}
        if data.get('id') not in live or not isinstance(data.get('facet'), str):
            raise ValueError('facet: a motif and a facet')
        mi.set_facet(data['id'], data['facet'], data.get('value') or None)
    elif act in ('facet_rename', 'facet_remove'):  # a genre renamed, or gone from every motif
        if not (data.get('facet') in mi.FACETS and isinstance(data.get('value'), str) and data['value'].strip()):
            raise ValueError(f'{act}: a facet and a value')
        if act == 'facet_rename':
            if not (isinstance(data.get('to'), str) and data['to'].strip()):
                raise ValueError('facet_rename: the new name')
            mi.facet_rename(data['facet'], data['value'], data['to'])
        else:
            mi.facet_remove(data['facet'], data['value'])
    elif act == 'facet_value':  # a new genre to sort by
        if not (isinstance(data.get('facet'), str) and isinstance(data.get('value'), str) and data['value'].strip()):
            raise ValueError('facet_value: a facet and a value')
        mi.add_facet_value(data['facet'], data['value'])
    elif act == 'same_claim':  # one claim told two ways: the variant folds into the kept one
        if not all(isinstance(data.get(k), str) and data[k].strip() for k in ('variant', 'canonical')):
            raise ValueError('same_claim: a variant and the claim to keep')
        mi.same_claim(data['variant'].strip(), data['canonical'].strip())
    elif act == 'new_with':  # a new motif made from claims dropped on it: each moved or copied from its motif, or filed
        name, claims = data.get('name'), data.get('claims')
        if not (isinstance(name, str) and name.strip() and isinstance(claims, list) and claims):
            raise ValueError('new_with: a name and claims')
        live = {e['id'] for e in mi.live(mi.load())}
        eid = mi.add(name)
        for c in claims:
            text, source = (c.get('claim') or '').strip(), c.get('source')
            if not text:
                continue
            if source in live and c.get('mode') == 'move':
                mi.move(text, source, eid)
            elif source in live:
                mi.also_file(text, source, eid)
            else:
                mi.file_by_hand({'claim': text, 'source': c.get('src', ''), 'ref': c.get('ref', '')}, eid)
    else:
        board_action(data)


def entities_page() -> str:
    """The names organizer (#165): one name per subject for the 'mentioned:' filters. Suggested merges first (a name
    inside another), then every subject with the names that point to it."""
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
    pairs = entities.suggestions()
    return render('names.html', '/entities', pairs=pairs[:40], name_count=len(counts),
                  subjects=sorted(subjects.items(), key=lambda kv: (-kv[1]['stories'], kv[0].lower())),
                  stories_of=lambda name: subjects.get(name, {}).get('stories', 0))


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


def organizer_action(data: dict):
    """Apply one organizer action; raises on anything unknown or missing."""
    from app.analysis import motif_index
    index = motif_index.load()
    known = lambda eid: eid in index['entries'] and not index['entries'][eid].get('merged_into')
    act = data.get('action')
    if act == 'rename' and known(data.get('id')) and data.get('name', '').strip():
        motif_index.rename(data['id'], data['name'])
    elif act == 'merge' and known(data.get('source')) and known(data.get('target')):
        motif_index.merge(data['source'], data['target'])
    elif act == 'related' and known(data.get('a')) and known(data.get('b')):
        motif_index.relate(data['a'], data['b'])
    elif act == 'kind_of' and known(data.get('child')) and known(data.get('parent')):
        motif_index.set_parent(data['child'], data['parent'])
    elif act == 'not_same' and known(data.get('a')) and known(data.get('b')):
        motif_index.not_same(data['a'], data['b'])
    elif act == 'delete' and known(data.get('id')):
        motif_index.delete(data['id'])
    elif act == 'move' and data.get('claim') and known(data.get('source')) \
            and (data.get('target') == 'new' or known(data.get('target'))):
        motif_index.move(data['claim'], data['source'], data['target'])
    elif act == 'add' and data.get('name', '').strip():
        motif_index.add(data['name'])
    else:
        raise ValueError(f'unknown action or motif: {data}')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/checkpoints.json'):
            from app.analysis import curation_db
            return self.send_json(curation_db.checkpoints())
        if self.path.startswith('/undo.json'):
            found = last_undo()
            return self.send_json({'what': found[1]['what'] if found else None})
        if self.path.startswith('/claims.json'):
            from urllib.parse import urlparse, parse_qs
            from app.analysis import motif_index
            q = parse_qs(urlparse(self.path).query).get('q', [''])[0].lower().split()
            found = [c for c in motif_index.searchable_claims() if all(w in c['claim'].lower() for w in q)]
            return self.send_json(sorted(found, key=lambda c: (bool(c['motifs']), c['claim']))[:60])
        if self.path.startswith('/claim-detail.json'):
            from urllib.parse import urlparse, parse_qs
            return self.send_json(claim_detail(parse_qs(urlparse(self.path).query).get('claim', [''])[0]))
        if self.path.startswith('/motif-similar.json'):
            from urllib.parse import urlparse, parse_qs
            from app.analysis import motif_index
            eid = parse_qs(urlparse(self.path).query).get('id', [''])[0]
            if eid not in {e['id'] for e in motif_index.live(motif_index.load())}:
                self.send_error(404)
                return
            return self.send_json(motif_index.similar(eid))
        if self.path.startswith('/claim-similar.json'):
            from urllib.parse import urlparse, parse_qs
            from app.analysis import motif_index
            return self.send_json(motif_index.similar_claims(parse_qs(urlparse(self.path).query).get('claim', [''])[0]))
        if self.path.startswith('/motif-export'):  # ?format=json|csv|md|ttl&scope=verified|all, as a download
            from urllib.parse import urlparse, parse_qs
            from app.analysis import motif_export
            q = parse_qs(urlparse(self.path).query)
            fmt, scope = q.get('format', ['json'])[0], q.get('scope', ['verified'])[0]
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
        if self.path.startswith('/workbench-metrics.json'):
            from app.analysis import motif_index
            return self.send_json(motif_index.metrics_history())
        if self.path.startswith('/workbench.json'):
            return self.send_json(workbench_state())
        if self.path.startswith('/workbench-queue.json'):
            from urllib.parse import urlparse, parse_qs
            try:
                return self.send_json(workbench_queue(parse_qs(urlparse(self.path).query).get('kind', [''])[0]))
            except ValueError as e:
                return self.send_json_error(404, str(e))
        if self.path.startswith('/motif-board.json'):
            from app.analysis import motif_index
            return self.send_json(motif_index.board())
        path = self.path.split('?')[0]
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
        body = (render(page_of, path) if page_of else motif_page() if path.startswith('/motifs') else entities_page() if path.startswith('/entities')
                else page())
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
        self._undo = (undo_path, read_text(undo_path)) if undo_path else None
        if self.path == '/workbench':
            by = data.pop('by', None)  # an action someone else made at the person's request (claude, by MCP)
            by = by if by in BY else None
            try:
                before = motif_context(data if data.get('action') != 'batch' else (data.get('steps') or [{}])[0])
                workbench_action(data)
                log_curation('motif workbench', data, before, by)
                steps = data['steps'] if data.get('action') == 'batch' else [data]
                self.remember(data if data.get('action') != 'batch' else
                              {'action': f"{len(data['steps'])} changes: {data['steps'][0].get('action')}…"}, before, by,
                              [x['proposal'] for x in steps if isinstance(x, dict) and x.get('proposal')])
            except (ValueError, KeyError) as e:
                self.remember({'action': 'part of a change that failed'}, {}, by)  # a batch stopped midway: still undoable
                return self.send_json_error(400, str(e))
            return self.send_json(workbench_state())
        if self.path == '/motif-board':
            from app.analysis import motif_index
            try:
                before = motif_context(data)
                board_action(data)
                log_curation('motif board', data, before)
                self.remember(data, before)
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e)[:200])
                return
            return self.send_json(motif_index.board())
        if self.path in ('/motif-index', '/entities'):
            try:
                if self.path == '/motif-index':
                    before = motif_context(data)
                    organizer_action(data)
                    log_curation('motif organizer', data, before)
                    self.remember(data, before)
                else:
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
        if self.path == '/motif-verdict':
            from app.analysis import motif_index
            try:
                before = motif_context(data)
                motif_index.check(data.get('claim', ''), data.get('id', ''), data.get('answer', ''))
                log_curation('motif check', data, before)
                self.remember(data, before)
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e)[:200])
                return
            data['at'] = dt.now().isoformat(timespec='seconds')
            with open(MOTIF_VERDICTS, 'a') as f:
                f.write(json.dumps({k: data[k] for k in ('claim', 'id', 'answer', 'at')}) + '\n')
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
            apply_label(data)  # straight onto the headline; the file keeps the record for agreement scores
        except (ValueError, KeyError) as e:
            self.send_error(400, str(e)[:200])
            return
        data['at'] = dt.now().isoformat(timespec='seconds')
        os.makedirs(FOLDER, exist_ok=True)
        with open(VERDICTS, 'a') as f:
            f.write(json.dumps(data) + '\n')
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    port = parser.parse_args().port
    print(f'Label check on http://0.0.0.0:{port} (Ctrl-C to stop)')
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
