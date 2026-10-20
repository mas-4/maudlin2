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
       ('/dashboard', '📈 Dashboard', 'main'), ('/experiments', '🧪 Experiments', 'main'), ('/flow', '🌊 Flow', 'main'), ('/live', '🧠 Live', 'main'),
       ('/motifs', '✅ check', 'motifs'), ('/motif-empty', '🫙 empty', 'motifs'),
       ('/motif-notes', '📝 notes', 'motifs'),
       ('/', '🏷️ label check', 'other'), ('/entities', '👥 names', 'other')]
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
    entries = mi.load()['entries']
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
        mi.relate(data['a'], data['b'], act == 'relate', data['note'] if isinstance(data.get('note'), str) else None)
    elif act == 'not_this' and data.get('id') in live and isinstance(data.get('text'), str):
        mi.set_not_this(data['id'], data['text'])
    elif act == 'carrying' and text('claim') and data.get('id') in live and isinstance(data.get('text'), (str, list)):
        mi.set_carrying(data['claim'], data['id'], data['text'])  # the tellers' words that carry it, per filing
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
    elif act == 'watch' and data.get('id') in live:  # a sink for plain reports, its claims watched (Straight news)
        mi.set_watch(data['id'], data.get('on', True) is not False)
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
        for eid in [data.get('id')] + list(data.get('ids') or []):  # its first motif, or a proposed family's
            if eid in live:
                mi.group_member(eid, gid)
    elif act == 'group_rename' and data.get('group') in index.get('groups', {}) and text('name'):
        mi.group_rename(data['group'], data['name'])
    elif act == 'group_note' and data.get('group') in index.get('groups', {}):
        mi.group_note(data['group'], data.get('note') or '')
    elif act == 'facet_note' and isinstance(data.get('facet'), str) and isinstance(data.get('value'), str):
        mi.facet_note(data['facet'], data['value'], data.get('note') or '')
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
    state['proposals'] = len(mp.open_proposals())  # the 💡 tab's count
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
                           'tally': sure_tally()} if sure else None
    return state


def filing_fits() -> dict:
    """Each unchecked filing's fit, as the hourly run left it on the filing (filing_confidence.refresh: the checker
    never asks the models itself)"""
    from app.analysis import motif_index as mi
    return {f"{mi.key(c['claim'])}|{e['id']}": c['fit'] for e in mi.live(mi.load()) for c in e['claims']
            if not c.get('checked') and c.get('fit') is not None}


def check_queue() -> list[dict]:
    """Every filing nobody has checked, each with its fit (the chance the person keeps it; only in their own motifs),
    the claims the model is least sure of first (a fit nearest even, by the claim's least likely filing): E6 (Oct 9)
    found the person's checks teach it most in that order, 150 of them as much as ~550 at random or more likeliest
    first (the order before). The sure ones still pass in one step from their own fold"""
    from app.analysis import filing_confidence as fc, motif_index as mi
    items = mi.to_check()
    fits = filing_fits()
    index = mi.load()
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


def sure_tally(days: int = SURE_TALLY_DAYS) -> list[dict]:
    """How the sure claims fared with the person, a day at a time, newest first: [{'day', 'clean', 'needed'}] (Oct 18,
    the person: "I feel like I'm having to heavily police the sure claims"; the held-out test said 95% right, but it
    counts only filings passed or taken out, and that day 9 of about 95 sure claims were held). A sure claim is clean
    when all of it passed; it needed the person when one of its sure filings was unticked, taken out, or the claim held.
    Holds logged before the ✅ sure tab marked its own count when all the claim's filings are sure now"""
    by = sure_tally_claims(days)
    return [{'day': d, 'clean': len(by[d]['clean']), 'needed': len(by[d]['needed'])} for d in sorted(by, reverse=True)]


def sure_tally_claims(days: int = SURE_TALLY_DAYS) -> dict:
    """sure_tally's claims: {day: {'clean' and 'needed': {claim key: {'claim', 'ids': the sure filings' motifs}}}}
    (Baron Munchausen, F24, scores them again)"""
    from app.analysis import curation_db, motif_index as mi
    since = (dt.now() - td(days=days)).strftime('%Y-%m-%d')
    index = mi.load()
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
    real = set(mi.load()['claims'])
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
            for e in mi.live(mi.load()) for c in e['claims'] if doubted(e, c, hand, recent)]
    rows = sorted(rows, key=lambda r: r['fit'])
    from app.analysis import filing_confidence as fc
    index = mi.load()
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
    index = mi.load()
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
        e = mi.load()['entries'].get(eid)
        c = next((c for c in (e or {}).get('claims', []) if c['claim'] == claim), None)
        if not c or (kind == 't' and c.get('checked')) or (kind == 'd' and (c.get('checked') != 'yes' or c.get('rechecked'))):
            return None
        return waiting.get(key) or {'kind': 'torn' if kind == 't' else 'doubted', 'id': eid, 'name': e['name'], 'claim': claim,
                                    'source': c.get('source', ''), 'fit': c.get('fit'), 'key': key,
                                    'better': fc.better(mi.load(), claim)}
    if kind == 'n':
        e = mi.load()['entries'].get(rest)
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
    index = mi.load()
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
        index = mi.load()
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


def _with_made(x, made: list[str]):
    """A batch step with "$1", "$2"… replaced by the motifs the batch's earlier steps made"""
    if isinstance(x, dict):
        return {k: _with_made(v, made) for k, v in x.items()}
    if isinstance(x, list):
        return [_with_made(v, made) for v in x]
    if isinstance(x, str) and x[:1] == '$' and x[1:].isdigit():
        if not 0 < int(x[1:]) <= len(made):
            raise ValueError(f'{x}: no motif made that early in the batch')
        return made[int(x[1:]) - 1]
    return x


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
    from app.analysis import motif_index as mi
    act = data.get('action')
    if act in ('telling', 'telling_reject'):  # 🧩 a flabby motif's telling made a motif of its own (tellings.py)
        from app.analysis import tellings
        if act == 'telling_reject':
            tellings.reject(data.get('key'))
        else:
            claims = [c for c in data.get('claims') or [] if isinstance(c, str)]
            data['id'] = tellings.make(data.get('parent', ''), data.get('name', ''), claims, data.get('note') or '',
                                       data.get('move', True) is not False, data.get('key'))
        return
    if act in ('split', 'split_reject'):  # the claim organizer's (claim_organizer.py), or a person's own split: its own
        from app.analysis import claim_organizer as co  # action, never read as "not this motif"
        why = data['why'].strip() if isinstance(data.get('why'), str) and data['why'].strip() else None
        if act == 'split_reject':
            co.reject_split(data.get('proposal', ''), why)
        else:  # the children file at the next hourly run (refile_pending), into the claims to judge
            done = co.apply_split(data.get('proposal') or None, data.get('children'), why,
                                  claim=None if data.get('proposal') else data.get('claim'), refile=False)
            data['ids'] = done.get('ids', [])  # the motifs the claim left, for the log
        return
    if data.get('proposal'):  # a proposal approved (its own action, carried out as usual) or rejected
        from app.analysis import motif_proposals as mp
        if act != 'proposal_reject':
            workbench_action({**{k: v for k, v in data.items() if k != 'proposal'}, 'proposed': True})
        mp.decide(data['proposal'], 'rejected' if act == 'proposal_reject' else 'approved',
                  data['why'] if isinstance(data.get('why'), str) else None,
                  None if act == 'proposal_reject' else {k: v for k, v in data.items() if k not in ('proposal', 'why')})
        return
    if act == 'batch':
        steps = data.get('steps')
        if not isinstance(steps, list) or not steps or any(not isinstance(x, dict) or x.get('action') == 'batch' for x in steps):
            raise ValueError('a batch is a list of actions')
        made = []  # motifs made by earlier steps: later steps name them "$1", "$2"… (Oct 9, for the MCP)
        with mi.batched():  # the index saved once at the end, not once a step (Oct 19: 29 steps took over a minute)
            for n, step in enumerate(steps):
                steps[n] = step = _with_made(step, made)  # the real ids, so the log has them
                had = set(mi.load()['entries'])
                try:
                    workbench_action(step)
                except (ValueError, KeyError) as e:
                    e.done = steps[:n]  # the steps that ran stay done: the caller logs them
                    raise
                made += sorted(set(mi.load()['entries']) - had)
    elif act in ('hold', 'unhold'):  # a claim kept aside to look at later, out of the queues; no verdict
        if not isinstance(data.get('claim'), str) or not data['claim'].strip():
            raise ValueError(f'{act}: a claim')
        mi.hold(data['claim'], act == 'hold')
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
        # no claims at all: a proposed motif kept as a seed, its claims not fitting (Oct 12)
        if not (isinstance(name, str) and name.strip() and isinstance(claims, list) and (claims or data.get('proposed'))):
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
        if (data.get('note') or '').strip():  # a 💡 proposed motif comes with its note and genre
            mi.set_note(eid, data['note'])
        if data.get('genre'):
            mi.set_facet(eid, 'genre', data['genre'])
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
        if self.path.startswith('/better.json'):  # where a weakly filed claim might belong instead
            from urllib.parse import urlparse, parse_qs
            from app.analysis import filing_confidence as fc, motif_index
            claim = parse_qs(urlparse(self.path).query).get('claim', [''])[0]
            return self.send_json(fc.better(motif_index.load(), claim))
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
        if self.path.startswith(('/experiments.json', '/experiment-paper.json', '/experiment-cases.json')):
            from urllib.parse import urlparse, parse_qs
            lab = experiments_lab()  # 🧪 the experiments page (scripts/experiments/lab.py)
            code = parse_qs(urlparse(self.path).query).get('code', [''])[0]
            if self.path.startswith('/experiments.json'):
                return self.send_json(lab.overview())
            return self.send_json(lab.paper(code) if self.path.startswith('/experiment-paper') else lab.cases(code))
        if self.path.startswith('/version.json'):  # the workbench's own code now: an open tab compares (code_version())
            return self.send_json({'version': code_version()})
        if self.path.startswith('/pace.json'):  # 📈 the person's pace against what arrives (pace())
            return self.send_json(pace())
        if self.path.startswith('/live.json'):  # 🧠 the filing pipeline as it runs (app/analysis/trace_view.py)
            from urllib.parse import urlparse, parse_qs
            from app.analysis import trace_view
            return self.send_json(trace_view.view({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}))
        if self.path.startswith('/flow.json'):  # 🌊 news stories into retellings over time (app/analysis/flow.py)
            from app.analysis import flow
            return self.send_json(flow.flow())
        if self.path.startswith('/dashboard.json'):  # 📈 everything at a glance (app/dashboard.py)
            from app import dashboard
            return self.send_json(dashboard.gather(fresh='fresh=1' in self.path))
        if self.path.startswith('/workbench-metrics.json'):
            from app.analysis import motif_index
            from app import health
            from app.utils.store import read_json
            return self.send_json({**motif_index.metrics_history(), 'health': read_json(health.HEALTH, None)})
        if self.path.startswith('/workbench.json'):
            return self.send_json(workbench_state())
        if self.path.startswith('/workbench-queue.json'):
            from urllib.parse import urlparse, parse_qs
            try:
                return self.send_json(workbench_queue(parse_qs(urlparse(self.path).query).get('kind', [''])[0]))
            except ValueError as e:
                return self.send_json_error(404, str(e))
        if self.path.startswith('/motif-claim-map.json'):  # the map's 🧲 claims mode
            from app.analysis import claim_map
            return self.send_json(claim_map.cached())
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
        body = (render(page_of, path, undo=page_of not in ('dashboard.html', 'experiments.html', 'flow.html', 'live.html')) if page_of else motif_page() if path.startswith('/motifs') else entities_page() if path.startswith('/entities')
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
        self._undo = (undo_path, read_text(undo_path)) if undo_path else None
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
        if self.path in ('/motif-index', '/entities'):
            try:
                if self.path == '/motif-index':
                    before = motif_context(data)
                    before.update(decision_fits(data))
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
                before.update(decision_fits(data))
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
