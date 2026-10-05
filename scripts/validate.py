"""Check the language model's headline labels by eye (#121): a small local page, never part of the site or deployed.

Run it, open http://<this machine>:8766 on any device on the network, and for each headline mark the model's mood,
spice (loaded wording) and feelings right, or pick what they should be. Verdicts are appended to
data/validation/verdicts.jsonl (one line per headline, with the model's labels at the time), and the page's footer
keeps a running agreement count. Headlines are drawn from the last two days, spread evenly over the model's mood and
spice values so the rare ones (very grim, very loaded) get checked as often as the common ones.

    .venv/bin/python scripts/validate.py [--port 8766]
"""
import argparse
import html
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
    pct = lambda k: f"{100 * st[k][0] / st[k][1]:.0f}% of {st[k][1]}" if st[k][1] else '—'

    def buttons(name, options, model):
        return ''.join(f'<button type="button" data-measure="{name}" data-value="{k}" class="{"model" if k == model else ""}">'
                       f'{e} {w}</button>' for k, (e, w) in options.items())

    cards = []
    for it in items:
        feel = ''.join(f'<button type="button" data-measure="feelings" data-value="{e}" class="{"model" if e in it["feelings"] else ""}">'
                       f'{EMOTION_EMOJI[e]} {e}</button>' for e in FEELINGS)
        cards.append(f"""
<section class="card" data-id="{it['headline_id']}" data-model='{html.escape(json.dumps({k: it[k] for k in ("mood", "spice", "feelings")}))}'>
  <p class="outlet">{html.escape(it['agency'])}</p>
  <h2><a href="{html.escape(it['url'] or '#')}" target="_blank" rel="noopener">{html.escape(it['title'])}</a></h2>
  <div class="row"><b>mood</b> <span class="said">model: {MOODS[it['mood']][0]} {MOODS[it['mood']][1]}</span>
    <button type="button" class="ok" data-ok="mood">✓ right</button><span class="pick">{buttons('mood', MOODS, it['mood'])}</span></div>
  <div class="row"><b>spice</b> <span class="said">model: {SPICES[it['spice']][0]} {SPICES[it['spice']][1]}</span>
    <button type="button" class="ok" data-ok="spice">✓ right</button><span class="pick">{buttons('spice', SPICES, it['spice'])}</span></div>
  <div class="row"><b>feelings</b> <span class="said">model: {' '.join(EMOTION_EMOJI[e] + ' ' + e for e in it['feelings']) or 'none'}</span>
    <button type="button" class="ok" data-ok="feelings">✓ right</button><span class="pick multi">{feel}</span></div>
  <button type="button" class="save" disabled>save</button>
</section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Label check</title><style>
:root {{ --ink: #1f1f2e; --paper: #fffdf6; --ok: #00c2a8; --no: #ff4fa3; }}
body {{ font-family: system-ui, sans-serif; background: var(--paper); color: var(--ink); margin: 0 auto; max-width: 760px; padding: 16px; }}
.card {{ border: 2px solid var(--ink); border-radius: 12px; padding: 12px 14px; margin: 14px 0; background: #fff; box-shadow: 4px 4px 0 #ffc400; }}
.card.done {{ opacity: .45; box-shadow: none; }}
.outlet {{ margin: 0; font-size: .85em; color: #555; }} h2 {{ font-size: 1.1em; margin: .2em 0 .6em; }} h2 a {{ color: var(--ink); }}
.row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: .45em 0; }} .row b {{ width: 4.5em; }}
.said {{ font-size: .9em; color: #444; margin-right: 4px; }}
button {{ font: inherit; font-size: .85em; border: 1.5px solid var(--ink); border-radius: 999px; background: #fff; padding: 3px 9px; cursor: pointer; }}
button.model {{ outline: 2px dashed #8a8f98; outline-offset: 1px; }}
button.chosen {{ background: var(--no); color: #fff; }} button.ok.chosen {{ background: var(--ok); }}
.save {{ margin-top: .4em; font-weight: 700; }} .save:disabled {{ opacity: .4; cursor: default; }}
footer {{ font-size: .9em; color: #444; margin: 1.5em 0; }}
</style></head><body>
<nav><b>Label check</b> <a href="/motifs">Motif check</a> <a href="/motif-index">Motif organizer</a></nav>
<h1>Label check</h1>
<p>Is the model right? Tap ✓ for a label that's right, or the value it should be (dashed: the model's pick; tapping
that counts as ✓). Feelings: tap every one the headline is likely to stir. Save each card; reload for more.</p>
{''.join(cards) or '<p>Nothing left to check from the last two days.</p>'}
<footer>So far: mood right {pct('mood')}, spice right {pct('spice')}, feelings right {pct('feelings')}
({st['headlines']} headlines). Most common mood misses (model, should be): {st['mood_misses']}</footer>
<script>
document.querySelectorAll('.card').forEach((card) => {{
  const verdict = {{}};
  const save = card.querySelector('.save');
  const ready = () => {{ save.disabled = !['mood', 'spice', 'feelings'].every((m) => m in verdict); }};
  card.querySelectorAll('button.ok').forEach((b) => b.addEventListener('click', () => {{
    const m = b.dataset.ok; verdict[m] = {{ok: true}};
    card.querySelectorAll(`[data-measure="${{m}}"]`).forEach((x) => x.classList.remove('chosen'));
    b.classList.add('chosen'); ready();
  }}));
  card.querySelectorAll('[data-measure]').forEach((b) => b.addEventListener('click', () => {{
    const m = b.dataset.measure;
    card.querySelector(`button.ok[data-ok="${{m}}"]`).classList.remove('chosen');
    if (m === 'feelings') {{
      b.classList.toggle('chosen');
      const picked = [...card.querySelectorAll('[data-measure="feelings"].chosen')].map((x) => x.dataset.value);
      const model = JSON.parse(card.dataset.model).feelings;
      const same = picked.length === model.length && picked.every((e) => model.includes(e));
      if (picked.length) verdict.feelings = same ? {{ok: true}} : {{ok: false, should: picked}}; else delete verdict.feelings;
    }} else {{
      card.querySelectorAll(`[data-measure="${{m}}"]`).forEach((x) => x.classList.toggle('chosen', x === b));
      const model = JSON.parse(card.dataset.model)[m];
      // Picking the model's own value is agreeing with it
      verdict[m] = Number(b.dataset.value) === model ? {{ok: true}} : {{ok: false, should: Number(b.dataset.value)}};
    }}
    ready();
  }}));
  save.addEventListener('click', async () => {{
    const body = {{headline_id: Number(card.dataset.id), model: JSON.parse(card.dataset.model), ...verdict}};
    const r = await fetch('/verdict', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)}});
    if (r.ok) {{ card.classList.add('done'); save.textContent = 'saved'; save.disabled = true; }}
  }});
}});
</script></body></html>"""


MOTIFS = os.path.join(FOLDER, 'motifs')  # the blind test of motif picking (claims.json, picks-*.json)
MOTIF_VERDICTS = os.path.join(FOLDER, 'motif_verdicts.jsonl')
MOTIF_BATCH = 10


def motif_questions() -> list[dict]:
    """Every distinct (claim, motif) a model or Claude picked, not yet answered, in a fixed shuffled order. Which
    model picked it is never shown."""
    import glob
    try:
        claims = {str(c['id']): c for c in json.load(open(os.path.join(MOTIFS, 'claims.json')))}
    except OSError:
        return []
    picked = set()
    for path in glob.glob(os.path.join(MOTIFS, 'picks-*.json')):
        picked |= {(cid, code) for cid, code in json.load(open(path)).items() if code and code != 'none'}
    try:
        with open(MOTIF_VERDICTS) as f:
            done = {(v['claim'], v['code']) for v in map(json.loads, f) if v}
    except OSError:
        done = set()
    todo = sorted(picked - done)
    random.Random(4).shuffle(todo)
    out = []
    for cid, code in todo:
        c = claims.get(cid)
        entry = next((x for x in (c or {}).get('candidates', []) if x['code'] == code), None)
        if c and entry:
            out.append({'claim_id': cid, 'claim': c['claim'], 'kind': c['kind'], 'source': c.get('source', ''),
                        'title': c.get('title', ''), 'code': code, 'text': entry['text']})
    return out


CHAPTER_NAMES = {'A': 'Mythological motifs', 'B': 'Animals', 'C': 'Tabu', 'D': 'Magic', 'E': 'The dead',
                 'F': 'Marvels', 'G': 'Ogres', 'H': 'Tests', 'J': 'The wise and the foolish', 'K': 'Deceptions',
                 'L': 'Reversal of fortune', 'M': 'Ordaining the future', 'N': 'Chance and fate', 'P': 'Society',
                 'Q': 'Rewards and punishments', 'R': 'Captives and fugitives', 'S': 'Unnatural cruelty', 'T': 'Sex',
                 'U': 'The nature of life', 'V': 'Religion', 'W': 'Traits of character', 'X': 'Humor',
                 'Z': 'Miscellaneous groups of motifs'}


def motif_page() -> str:
    todo = motif_questions()
    cards = []
    for q in todo[:MOTIF_BATCH]:
        where = (f'<p class="outlet">fact-checked by {html.escape(q["source"])}: {html.escape(q["title"])}</p>'
                 if q['kind'] == 'fact-check' else '<p class="outlet">retold online (the model\'s summary)</p>')
        cards.append(f"""
<section class="card" data-claim="{q['claim_id']}" data-code="{html.escape(q['code'])}">
  {where}
  <h2>{html.escape(q['claim'])}</h2>
  <p>Is this a modern instance of <b>{html.escape(q['code'])}</b>: <i>{html.escape(q['text'])}</i>
    <span class="said">({html.escape(q['code'][0])}, {CHAPTER_NAMES.get(q['code'][0], '')})</span>?</p>
  <div class="row"><button type="button" data-a="yes">✓ yes</button><button type="button" data-a="no">✗ no</button>
    <button type="button" data-a="unsure">🤷 not sure</button></div>
</section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motif check</title><style>
body {{ font-family: system-ui, sans-serif; background: #fffdf6; color: #1f1f2e; margin: 0 auto; max-width: 760px; padding: 16px; }}
.card {{ border: 2px solid #1f1f2e; border-radius: 12px; padding: 12px 14px; margin: 14px 0; background: #fff; box-shadow: 4px 4px 0 #ffc400; }}
.card.done {{ opacity: .45; box-shadow: none; }} .outlet {{ margin: 0; font-size: .85em; color: #555; }}
h2 {{ font-size: 1.1em; margin: .3em 0 .5em; }} .said {{ font-size: .85em; color: #555; }}
.row {{ display: flex; gap: 8px; }} button {{ font: inherit; border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 4px 12px; cursor: pointer; }}
nav a {{ margin-right: 1em; }}
</style></head><body>
<nav><a href="/">Label check</a> <b>Motif check</b> <a href="/motif-index">Motif organizer</a></nav>
<h1>Motif check</h1>
<p>Each card is a claim and one entry from Thompson's Motif-Index. Is the claim, as the people telling it tell it, a modern
version of that motif: the same situation or trick, with today's people and things in place of the old ones? Judge
only the story's shape, not whether it's true or whether you agree. A shared word isn't enough. You're
not told which model suggested it. {len(todo)} left; tap an answer and the card is saved. Reload for more.</p>
{''.join(cards) or '<p>Nothing left to check.</p>'}
<script>
document.querySelectorAll('.card').forEach((card) => card.querySelectorAll('button').forEach((b) => b.addEventListener('click', async () => {{
  const r = await fetch('/motif-verdict', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{claim: card.dataset.claim, code: card.dataset.code, answer: b.dataset.a}})}});
  if (r.ok) {{ card.classList.add('done'); card.querySelectorAll('button').forEach((x) => x.disabled = true); b.style.background = '#ffc400'; }}
}})));
</script></body></html>"""


def organizer_page() -> str:
    """The motif organizer: suggested merges first, then every entry to rename, merge, delete, or move claims out of."""
    from app.analysis import motif_index
    index = motif_index.load()
    entries = sorted(motif_index.live(index), key=lambda e: (-len(e['claims']), e['id']))
    by_id = {e['id']: e for e in entries}
    esc = html.escape

    def claims_of(e, n=3):
        return ''.join(f'<li>{esc(c["claim"][:140])} <span class="said">{esc(c["source"] if c["source"] != "narrative" else "people online")}</span></li>'
                       for c in e['claims'][:n])
    try:
        pairs = motif_index.suggestions()
    except Exception as e:  # noqa: Ollama down: no suggestions, the rest still works
        pairs, note = [], f'(suggestions unavailable: {esc(str(e))})'
    else:
        note = ''
    suggest = ''.join(f"""
<section class="card pair">
  <p class="outlet">similar names ({sim:.2f})</p>
  <div class="two"><div><b>{a} 🧩 {esc(by_id[a]['name'])}</b><ul>{claims_of(by_id[a])}</ul></div>
    <div><b>{b} 🧩 {esc(by_id[b]['name'])}</b><ul>{claims_of(by_id[b])}</ul></div></div>
  <div class="row"><button data-act="merge" data-source="{b}" data-target="{a}">⤵ merge into {a}</button>
    <button data-act="merge" data-source="{a}" data-target="{b}">⤵ merge into {b}</button>
    <button data-act="not_same" data-a="{a}" data-b="{b}">✗ not the same</button></div>
</section>""" for a, b, sim in pairs if a in by_id and b in by_id)
    cards = ''.join(f"""
<section class="card entry" id="{e['id']}" data-text="{esc((e['name'] + ' ' + ' '.join(c['claim'] for c in e['claims'])).lower())}">
  <p class="outlet">{e['id']} · {len(e['claims'])} claim{'' if len(e['claims']) == 1 else 's'} · first seen {e.get('first_seen', '')}{' · ✎ curated' if e.get('curated') else ''}</p>
  <div class="row"><input class="name" value="{esc(e['name'])}" size="60"><button data-act="rename" data-id="{e['id']}">rename</button></div>
  <ul>{''.join(f'<li>{esc(c["claim"][:160])} <span class="said">{esc(c["source"] if c["source"] != "narrative" else "people online")}</span> <button class="small" data-act="move" data-source="{e['id']}" data-claim="{esc(c["claim"])}">move to…</button></li>' for c in e['claims'])}</ul>
  <div class="row"><button data-act="merge_into" data-source="{e['id']}">⤵ merge into…</button>
    <button data-act="delete" data-id="{e['id']}">🗑 delete</button></div>
</section>""" for e in entries)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motif organizer</title><style>
body {{ font-family: system-ui, sans-serif; background: #fffdf6; color: #1f1f2e; margin: 0 auto; max-width: 900px; padding: 16px; }}
.card {{ border: 2px solid #1f1f2e; border-radius: 12px; padding: 10px 14px; margin: 12px 0; background: #fff; box-shadow: 4px 4px 0 #ffc400; }}
.pair {{ box-shadow: 4px 4px 0 #ff4fa3; }} .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.outlet, .said {{ font-size: .85em; color: #555; }} ul {{ margin: .4em 0; padding-left: 1.2em; }} li {{ margin: .2em 0; }}
.row {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: .4em 0; }} input {{ font: inherit; padding: 3px 6px; }}
button {{ font: inherit; font-size: .85em; border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 3px 10px; cursor: pointer; }}
button.small {{ font-size: .75em; padding: 1px 7px; }} nav a {{ margin-right: 1em; }} h2 {{ margin-top: 1.4em; }}
@media (max-width: 640px) {{ .two {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<nav><a href="/">Label check</a> <a href="/motifs">Motif check</a> <b>Motif organizer</b></nav>
<h1>Motif organizer</h1>
<p>Our own motif index: {len(entries)} motifs from {sum(len(e['claims']) for e in entries)} claims. A claim can carry up to three motifs. Merge
duplicates, rename to a reusable framing ("X is / isn't Y"), delete what isn't a motif, or move a claim that landed in
the wrong place. Renamed motifs keep your name; deleted motifs' claims aren't filed again. Changes go live with the
next site build.</p>
<h2>Suggested merges {note}</h2>
{suggest or '<p>No suggestions right now.</p>'}
<h2>Add a motif</h2>
<div class="row"><input id="new-name" size="60" placeholder="a reusable framing, e.g. the ruler is / isn't fit to lead"><button data-act="add">+ add</button></div>
<h2>All motifs</h2>
<p><input type="search" id="search" placeholder="search motifs and claims" size="40"></p>
{cards}
<script>
const post = async (body) => {{
  const r = await fetch('/motif-index', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)}});
  if (!r.ok) {{ alert('Failed: ' + await r.text()); return; }}
  const y = scrollY; location.reload(); setTimeout(() => scrollTo(0, y), 50);
}};
document.addEventListener('click', (ev) => {{
  const b = ev.target.closest('button[data-act]');
  if (!b) return;
  const d = b.dataset;
  if (d.act === 'rename') post({{action: 'rename', id: d.id, name: b.previousElementSibling.value}});
  else if (d.act === 'merge') post({{action: 'merge', source: d.source, target: d.target}});
  else if (d.act === 'not_same') post({{action: 'not_same', a: d.a, b: d.b}});
  else if (d.act === 'merge_into') {{ const t = prompt('Merge ' + d.source + ' into which motif? (its number, e.g. M012)'); if (t) post({{action: 'merge', source: d.source, target: t.trim().toUpperCase()}}); }}
  else if (d.act === 'delete') {{ if (confirm('Delete ' + d.id + '? Its claims won\'t be filed again.')) post({{action: 'delete', id: d.id}}); }}
  else if (d.act === 'move') {{ const t = prompt('Move this claim to which motif? (its number, or "new")'); if (t) post({{action: 'move', claim: d.claim, source: d.source, target: t.trim() === 'new' ? 'new' : t.trim().toUpperCase()}}); }}
  else if (d.act === 'add') {{ const n = document.getElementById('new-name').value.trim(); if (n) post({{action: 'add', name: n}}); }}
}});
document.getElementById('search').addEventListener('input', (ev) => {{
  const q = ev.target.value.trim().toLowerCase();
  document.querySelectorAll('.entry').forEach((c) => {{ c.hidden = q && !c.dataset.text.includes(q); }});
}});
</script></body></html>"""


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
        body = (organizer_page() if self.path.startswith('/motif-index') else motif_page()
                if self.path.startswith('/motifs') else page()).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/motif-index':
            try:
                organizer_action(data)
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e)[:200])
                return
            self.send_response(204)
            self.end_headers()
            return
        if self.path == '/motif-verdict':
            if data.get('answer') not in ('yes', 'no', 'unsure') or not data.get('code'):
                self.send_error(400)
                return
            data['at'] = dt.now().isoformat(timespec='seconds')
            with open(MOTIF_VERDICTS, 'a') as f:
                f.write(json.dumps({k: data[k] for k in ('claim', 'code', 'answer', 'at')}) + '\n')
            self.send_response(204)
            self.end_headers()
            return
        if self.path != '/verdict':
            self.send_error(404)
            return
        if not isinstance(data.get('headline_id'), int):
            self.send_error(400)
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
