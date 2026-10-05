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
<nav><b>Label check</b> <a href="/motifs">Motif check</a> <a href="/motif-index">Motif organizer</a> <a href="/motif-board">Motif board</a> <a href="/entities">Names</a></nav>
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


MOTIF_VERDICTS = os.path.join(FOLDER, 'motif_verdicts.jsonl')  # a record of every answer, for agreement scores
MOTIF_BATCH = 10


def motif_page() -> str:
    """The motif check: is each claim filed in our motif index an instance of its motif? Answers apply at once."""
    from app.analysis import motif_index
    todo = motif_index.to_check()
    esc = html.escape
    cards = []
    for q in todo[:MOTIF_BATCH]:
        said = 'retold online (the model\'s summary)' if q['source'] == 'narrative' else f'fact-checked by {esc(q["source"])}'
        others = ''.join(f'<li>{esc(o[:150])}</li>' for o in q['others'])
        cards.append(f"""
<section class="card" data-claim="{esc(q['claim'])}" data-id="{q['id']}">
  <p class="outlet">{said}</p>
  <h2>{esc(q['claim'])}</h2>
  <p>Is this an instance of <b>🧩 {esc(q['name'])}</b> <span class="said">({q['id']}, {q['size']} claim{'' if q['size'] == 1 else 's'})</span>?</p>
  {f'<p class="said">Also filed there:</p><ul class="said">{others}</ul>' if others else ''}
  <div class="row"><button type="button" data-a="yes">✓ yes</button><button type="button" data-a="no">✗ no, take it out</button>
    <button type="button" data-a="unsure">🤷 not sure</button></div>
</section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motif check</title><style>
body {{ font-family: system-ui, sans-serif; background: #fffdf6; color: #1f1f2e; margin: 0 auto; max-width: 760px; padding: 16px; }}
.card {{ border: 2px solid #1f1f2e; border-radius: 12px; padding: 12px 14px; margin: 14px 0; background: #fff; box-shadow: 4px 4px 0 #ffc400; }}
.card.done {{ opacity: .45; box-shadow: none; }} .outlet {{ margin: 0; font-size: .85em; color: #555; }}
h2 {{ font-size: 1.1em; margin: .3em 0 .5em; }} .said {{ font-size: .85em; color: #555; }} ul.said {{ margin: .2em 0 .5em; }}
.row {{ display: flex; flex-wrap: wrap; gap: 8px; }} button {{ font: inherit; border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 4px 12px; cursor: pointer; }}
nav a {{ margin-right: 1em; }}
</style></head><body>
<nav><a href="/">Label check</a> <b>Motif check</b> <a href="/motif-index">Motif organizer</a> <a href="/motif-board">Motif board</a> <a href="/entities">Names</a></nav>
<h1>Motif check</h1>
<p>Each card is a claim and a motif our index filed it under. Is the claim, as the people telling it tell it, an
instance of that motif: the same kind of story, whoever it's told about? Judge the story's shape, not whether it's
true. Answers apply at once: <b>no</b> takes the claim out of that motif for good (a motif left empty goes; a claim
left with no motif is filed again next run, elsewhere). The most-used motifs come first. {len(todo)} filings
unchecked; reload for more.</p>
{''.join(cards) or '<p>Nothing left to check.</p>'}
<script>
document.querySelectorAll('.card').forEach((card) => card.querySelectorAll('button').forEach((b) => b.addEventListener('click', async () => {{
  const r = await fetch('/motif-verdict', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{claim: card.dataset.claim, id: card.dataset.id, answer: b.dataset.a}})}});
  if (r.ok) {{ card.classList.add('done'); card.querySelectorAll('button').forEach((x) => x.disabled = true); b.style.background = '#ffc400'; }}
  else alert('Failed: ' + await r.text());
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
    def side(me, other, claims):
        """One motif of a pair, with what this motif can do about the other, worded from its side"""
        m, o = by_id[me], by_id[other]
        return f"""<div class="side"><b>🧩 {esc(m['name'])}</b> <span class="said">{me} · {len(m['claims'])} claim{'' if len(m['claims']) == 1 else 's'}</span>
      <button class="small" data-act="rename_prompt" data-id="{me}" data-name="{esc(m['name'])}" title="rename">✎</button>
      <ul>{claims}</ul>
      <div class="side-acts"><span class="said">This one:</span>
        <button data-act="merge" data-source="{me}" data-target="{other}" title="{esc(m['name'])} goes; its claims join {esc(o['name'])}">⤵ merge into “{esc(o['name'])}”</button>
        <button data-act="kind_of" data-child="{me}" data-parent="{other}">⊂ is a kind of “{esc(o['name'])}”</button></div></div>"""

    def pair_card(a, b, header, claims_a, claims_b, shared=''):
        return f"""
<section class="card pair">
  <p class="outlet">{header}</p>
  {shared}
  <div class="two">{side(a, b, claims_a)}
    {side(b, a, claims_b)}</div>
  <div class="row both"><span class="said">The two:</span>
    <button data-act="related" data-a="{a}" data-b="{b}" title="near each other, but different stories">↔ related</button>
    <button data-act="not_same" data-a="{a}" data-b="{b}">✗ not the same</button></div>
</section>"""
    suggest = ''.join(pair_card(a, b, f'similar names ({sim:.2f})', claims_of(by_id[a]), claims_of(by_id[b]))
                      for a, b, sim in pairs if a in by_id and b in by_id)
    li = lambda texts, n: ''.join(f'<li>{esc(c[:n])}</li>' for c in texts) or '<li class="said">no others</li>'  # noqa: E731
    shared = ''.join(pair_card(p['a'], p['b'], f"filed together on {len(p['shared'])} claim{'' if len(p['shared']) == 1 else 's'}",
                               li(p['only_a'], 140), li(p['only_b'], 140),
                               f'<p class="said">Both hold:</p><ul class="bothclaims">{li(p["shared"], 160)}</ul>')
                     for p in motif_index.shared_pairs() if p['a'] in by_id and p['b'] in by_id)
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
.side {{ border: 1.5px dashed #ccc; border-radius: 10px; padding: 6px 10px; }} .side-acts {{ display: flex; flex-direction: column; align-items: flex-start; gap: 5px; margin-top: 6px; }}
.both {{ border-top: 1px dashed #ccc; padding-top: 6px; }} .bothclaims {{ background: #f4f1e6; border-radius: 8px; padding: 6px 6px 6px 24px; }}
.outlet, .said {{ font-size: .85em; color: #555; }} ul {{ margin: .4em 0; padding-left: 1.2em; }} li {{ margin: .2em 0; }}
.row {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: .4em 0; }} input {{ font: inherit; padding: 3px 6px; }}
button {{ font: inherit; font-size: .85em; border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 3px 10px; cursor: pointer; }}
button.small {{ font-size: .75em; padding: 1px 7px; }} nav a {{ margin-right: 1em; }} h2 {{ margin-top: 1.4em; }}
@media (max-width: 640px) {{ .two {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<nav><a href="/">Label check</a> <a href="/motifs">Motif check</a> <b>Motif organizer</b> <a href="/motif-board">Motif board</a> <a href="/entities">Names</a></nav>
<h1>Motif organizer</h1>
<p>Our own motif index: {len(entries)} motifs from {sum(len(e['claims']) for e in entries)} claims. Merge motifs that are one,
mark one a kind of another, or two as related (near each other, different stories); rename, delete what isn't a motif,
or move a claim that landed in the wrong place. Changes are saved at once and go live with the next site build.</p>
<h2>Filed together</h2>
<p class="said">Motifs the model filed on two or more of the same claims: judge them by what they hold, not their names.</p>
{shared or '<p>None right now.</p>'}
<h2>Similar names {note}</h2>
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
  else if (d.act === 'rename_prompt') {{ const n = prompt('Rename ' + d.id, d.name); if (n && n.trim() && n.trim() !== d.name) post({{action: 'rename', id: d.id, name: n.trim()}}); }}
  else if (d.act === 'merge') post({{action: 'merge', source: d.source, target: d.target}});
  else if (d.act === 'not_same') post({{action: 'not_same', a: d.a, b: d.b}});
  else if (d.act === 'kind_of') post({{action: 'kind_of', child: d.child, parent: d.parent}});
  else if (d.act === 'related') post({{action: 'related', a: d.a, b: d.b}});
  else if (d.act === 'merge_into') {{ const t = prompt('Merge ' + d.source + ' into which motif? (its number, e.g. M012)'); if (t) post({{action: 'merge', source: d.source, target: t.trim().toUpperCase()}}); }}
  else if (d.act === 'delete') {{ if (confirm('Delete ' + d.id + '? Its claims will not be filed under it again.')) post({{action: 'delete', id: d.id}}); }}
  else if (d.act === 'move') {{ const t = prompt('Move this claim to which motif? (its number, or "new")'); if (t) post({{action: 'move', claim: d.claim, source: d.source, target: t.trim() === 'new' ? 'new' : t.trim().toUpperCase()}}); }}
  else if (d.act === 'add') {{ const n = document.getElementById('new-name').value.trim(); if (n) post({{action: 'add', name: n}}); }}
}});
document.getElementById('search').addEventListener('input', (ev) => {{
  const q = ev.target.value.trim().toLowerCase();
  document.querySelectorAll('.entry').forEach((c) => {{ c.hidden = q && !c.dataset.text.includes(q); }});
}});
</script></body></html>"""


BOARD_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motif board</title><style>
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; background: #fffdf6; color: #1f1f2e; margin: 0; }
header { position: sticky; top: 0; z-index: 5; background: #fffdf6; border-bottom: 2px solid #1f1f2e; padding: 8px 14px; }
nav a { margin-right: 1em; } h1 { font-size: 1.2em; margin: .3em 0; display: inline-block; margin-right: 1em; }
.tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 4px; }
input, select, button { font: inherit; font-size: .9em; }
input[type=search] { padding: 4px 10px; border: 2px solid #1f1f2e; border-radius: 999px; min-width: 16em; }
button { border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 3px 10px; cursor: pointer; }
button.small { font-size: .75em; padding: 0 6px; }
main { display: grid; grid-template-columns: 230px 1fr; gap: 14px; padding: 14px; align-items: start; }
aside { position: sticky; top: 120px; max-height: calc(100vh - 140px); overflow: auto; }
.group { border: 2px solid #1f1f2e; border-radius: 10px; background: #fff; padding: 6px 10px; margin-bottom: 8px; cursor: pointer; }
.group.on { background: #ffe9a8; } .group .n { color: #555; font-size: .85em; float: right; }
.group.target, .motif.target { outline: 3px dashed #ff4fa3; outline-offset: 2px; }
.group.new { border-style: dashed; color: #555; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; align-items: start; }
.motif { border: 2px solid #1f1f2e; border-radius: 12px; background: #fff; margin: 0;
  box-shadow: 4px 4px 0 #00c2a8; }
.motif.one { box-shadow: 3px 3px 0 #ddd; }
.motif .head { padding: 7px 10px 4px; cursor: grab; border-bottom: 1px dashed #ccc; }
.motif .name { font-weight: 700; } .motif .meta { font-size: .78em; color: #666; }
.kindof { font-size: .78em; color: #5a3fc0; } .kinds { font-size: .78em; color: #5a3fc0; }
#choose button { font-size: .95em; padding: 5px 12px; } #choose button.add { background: #c8f7c5; font-weight: 700; }
.donebtn { float: right; margin-left: 6px; background: #c8f7c5; } .motif.isdone { opacity: .55; }
.newpill { font-size: .75em; background: #ff4fa3; color: #fff; border-radius: 999px; padding: 0 6px; margin-left: 4px; }
.motif .gpill { font-size: .75em; background: #ffe9a8; border-radius: 999px; padding: 0 6px; margin-left: 4px; }
.motif ul { list-style: none; margin: 0; padding: 4px 6px 6px; }
.motif li { font-size: .85em; padding: 3px 4px; border-radius: 6px; cursor: grab; display: flex; gap: 4px; align-items: baseline; }
.motif li:hover { background: #f4f1e6; }
.motif li.newclaim { background: #ffe0ef; border-left: 4px solid #ff4fa3; } .motif li .newtag { color: #c2185b; font-weight: 700; font-size: .8em; }
.motif li .txt { flex: 1; } .motif li .src { color: #777; font-size: .85em; white-space: nowrap; }
.motif li .ok { color: #00a37a; } .motif .acts { padding: 0 10px 8px; display: flex; gap: 5px; flex-wrap: wrap; }
.more { color: #555; cursor: pointer; font-size: .8em; padding: 0 10px 6px; }
.motif li .txt { cursor: pointer; } .motif li .txt:hover { text-decoration: underline dotted; }
.motif li, .motif .head { user-select: none; touch-action: manipulation; }
body.dragging, body.dragging * { cursor: grabbing !important; user-select: none; }
.ghost { display: none; position: fixed; z-index: 30; pointer-events: none; max-width: 320px; padding: 4px 10px; background: #ffc400;
  border: 2px solid #1f1f2e; border-radius: 10px; box-shadow: 3px 3px 0 #1f1f2e; font-size: .85em; }
#toast { display: none; position: fixed; z-index: 25; left: 50%; bottom: 18px; transform: translateX(-50%); background: #fffdf6;
  border: 2px solid #1f1f2e; border-radius: 12px; box-shadow: 4px 4px 0 #00c2a8; padding: 8px 14px; max-width: 94vw; }
dialog { border: 2px solid #1f1f2e; border-radius: 14px; box-shadow: 6px 6px 0 #ffc400; width: min(640px, 94vw); max-height: 86vh;
  padding: 12px 16px; background: #fffdf6; color: #1f1f2e; } dialog::backdrop { background: rgba(31, 31, 46, .35); }
dialog h2 { font-size: 1.05em; margin: .2em 2em .5em 0; } dialog .x { position: absolute; right: 10px; top: 8px; }
.now { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; } .now span { background: #e6f7f2; border: 1.5px solid #1f1f2e;
  border-radius: 999px; padding: 1px 8px; font-size: .85em; }
.pick { max-height: 46vh; overflow: auto; border-top: 1px dashed #ccc; margin-top: 6px; }
.pick div { display: flex; gap: 6px; align-items: center; padding: 4px 2px; border-bottom: 1px dashed #eee; }
.pick div .nm { flex: 1; } .pick div .ct { color: #777; font-size: .8em; }
.pick button.add, .acts button.add { background: #c8f7c5; font-weight: 700; }
.pick div.newfromq { background: #fff3c4; border-radius: 8px; }
.pick .simrow .meta { display: block; color: #666; font-size: .8em; } .meta { color: #666; font-size: .85em; font-weight: normal; }
@media (max-width: 700px) { main { grid-template-columns: 1fr; } aside { position: static; max-height: none; } }
</style></head><body>
<header>
<nav><a href="/">Label check</a> <a href="/motifs">Motif check</a> <a href="/motif-index">Motif organizer</a> <b>Motif board</b> <a href="/entities">Names</a></nav>
<h1>🧩 Motif board</h1><span id="stats"></span> <a href="/motif-empty" id="empty-link"></a>
<div class="tools">
  <input type="search" id="q" placeholder="search motifs and claims">
  <select id="sort"><option value="size">most claims</option><option value="few">fewest claims</option><option value="new">newest</option><option value="old">oldest</option><option value="az">A–Z</option></select>
  <label><input type="checkbox" id="multi"> only motifs with 2+ claims</label>
  <label><input type="checkbox" id="showdone"> show done</label>
  <button id="reset-done" title="Bring back every motif marked done">↺ reset done</button>
  <button id="add-motif">+ motif</button>
</div>
</header>
<main>
<aside>
  <p class="meta" style="font-size:.8em;color:#555;margin:0 0 6px">Drag a claim onto a motif to add it there, a motif onto another to merge them, make it a kind of the other or mark them related, or onto a group to file it. Click a claim for all its motifs. Tap a group to show only its motifs.</p>
  <div id="groups"></div>
</aside>
<section class="grid" id="grid"></section>
</main>
<div id="toast" role="status"></div>
<dialog id="choose"><div id="choose-body"></div></dialog>
<dialog id="similar"><button class="small x" data-close="1">✕</button><div id="similar-body"></div></dialog>
<dialog id="picker"><button class="small x" data-close="1">✕</button><div id="picker-body"></div></dialog>
<script>
let data = {groups: [], entries: []}, filter = 'all';
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const $ = (s) => document.querySelector(s);
const expanded = new Set();
async function act(body) {
  const r = await fetch('/motif-board', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!r.ok) { alert('Failed: ' + await r.text()); return; }
  data = await r.json(); render(); if (window.refreshUndo) refreshUndo();
}
function render() {
  const q = $('#q').value.trim().toLowerCase(), multi = $('#multi').checked, sort = $('#sort').value;
  const count = (g) => data.entries.filter((e) => (g === null ? !e.group : e.group === g)).length;
  const nEmpty = data.entries.filter((e) => !e.claims.length && !data.entries.some((x) => x.parent === e.id)).length;
  $('#empty-link').textContent = nEmpty ? `· ${nEmpty} empty motif${nEmpty === 1 ? '' : 's'}` : '';
  const showDone = $('#showdone').checked, left = data.entries.filter((e) => e.done !== 'done').length;
  $('#stats').textContent = `${data.entries.length} motifs · ${data.entries.reduce((n, e) => n + e.claims.length, 0)} filings · ${data.entries.filter((e) => e.claims.length > 1).length} with 2+ claims · ${left} to go`;
  const gs = [{id: 'all', name: 'All motifs', n: data.entries.length}, {id: 'none', name: 'Ungrouped', n: count(null)}]
    .concat(data.groups.map((g) => ({...g, n: count(g.id)})));
  $('#groups').innerHTML = gs.map((g) => `<div class="group${filter === g.id ? ' on' : ''}" data-g="${g.id}"><span class="n">${g.n}</span>${esc(g.name)}`
    + (g.id.startsWith('G') ? ` <button class="small" data-gact="rename">✎</button> <button class="small" data-gact="delete">🗑</button>` : '') + '</div>').join('')
    + `<div class="group new" data-g="+">+ new group</div><div class="group new" data-g="newmotif">+ new motif: drop a claim here</div>`;
  let list = data.entries.filter((e) => filter === 'all' || (filter === 'none' ? !e.group : e.group === filter))
    .filter((e) => !multi || e.claims.length > 1)
    .filter((e) => showDone || e.done !== 'done')
    .filter((e) => !q || (e.name + ' ' + e.claims.map((c) => c.claim).join(' ')).toLowerCase().includes(q));
  const newest = (a, b) => (b.first_seen || '').localeCompare(a.first_seen || '') || b.id.localeCompare(a.id);
  list.sort({az: (a, b) => a.name.localeCompare(b.name), new: newest, old: (a, b) => newest(b, a),
    few: (a, b) => a.claims.length - b.claims.length || newest(a, b),
    size: (a, b) => b.claims.length - a.claims.length || a.id.localeCompare(b.id)}[sort]);
  const gname = Object.fromEntries(data.groups.map((g) => [g.id, g.name]));
  $('#grid').innerHTML = list.map((e) => {
    // New claims (since the motif was marked done) first, so they're never hidden behind 'show all'
    const ordered = [...e.claims.filter((c) => c.new), ...e.claims.filter((c) => !c.new)];
    const shown = expanded.has(e.id) ? ordered : ordered.slice(0, Math.max(6, e.claims.filter((c) => c.new).length));
    return `<article class="motif${e.done === 'done' ? ' isdone' : ''}${e.claims.length < 2 ? ' one' : ''}" data-id="${e.id}">
      <div class="head">${e.done === 'done' ? '<button class="small donebtn" data-mact="undone" title="Show it again">↺ not done</button>'
          : '<button class="small donebtn" data-mact="done" title="Hide it: you\'re done with it">✓ done</button>'}<span class="name">${esc(e.name)}</span>${e.done === 'new' ? `<span class="newpill" title="Marked done, then new claims came in: they're highlighted, first">${e.claims.filter((c) => c.new).length} new since you looked</span>` : ''}${e.group ? `<span class="gpill">${esc(gname[e.group] || e.group)}</span>` : ''}
        ${e.parent ? `<div class="kindof">↳ kind of 🧩 ${esc((data.entries.find((x) => x.id === e.parent) || {}).name || e.parent)} <button class="small" data-mact="unparent" title="no longer a kind of it">✗</button></div>` : ''}
        ${(() => { const kids = data.entries.filter((x) => x.parent === e.id); return kids.length ? `<div class="kinds">kinds: ${kids.map((k) => esc(k.name)).join(', ')}</div>` : ''; })()}
        ${e.related.length ? `<div class="kinds">↔ related: ${e.related.map((r) => `${esc((data.entries.find((x) => x.id === r) || {}).name || r)} <button class="small" data-unrelate="${r}" title="not related">✗</button>`).join(' ')}</div>` : ''}
        <div class="meta">${e.id} · ${e.claims.length} claim${e.claims.length === 1 ? '' : 's'} · since ${esc(e.first_seen)}${e.curated ? ' · ✎ named by hand' : ''}</div></div>
      <ul>${shown.map((c) => `<li data-claim="${esc(c.claim)}" class="${c.new ? 'newclaim' : ''}">
        <span class="txt">${c.new ? '<span class="newtag">NEW </span>' : ''}${c.checked === 'yes' ? '<span class="ok" title="checked">✓</span> ' : ''}${esc(c.claim)}</span>
        <span class="src">${esc(c.source === 'narrative' ? 'online' : c.source)}</span>
        <button class="small" data-cact="out" title="take it out of this motif for good">✗</button></li>`).join('')}</ul>
      ${e.claims.length > 6 ? `<div class="more" data-more="1">${expanded.has(e.id) ? 'show fewer' : `show all ${e.claims.length}`}</div>` : ''}
      <div class="acts"><button class="small add" data-mact="more" title="the claims closest to this motif, to add fast">＋ more like this</button><button class="small" data-mact="rename">✎ rename</button>
        ${e.group ? '<button class="small" data-mact="ungroup">ungroup</button>' : ''}<button class="small" data-mact="delete">🗑</button></div></article>`;
  }).join('') || '<p>No motifs here.</p>';
}
document.addEventListener('click', (ev) => {
  const g = ev.target.closest('.group'), m = ev.target.closest('.motif'), b = ev.target.closest('button');
  if (g) {
    const gid = g.dataset.g, gact = b && b.dataset.gact;
    if (gact === 'rename') { const n = prompt('Rename the group', (data.groups.find((x) => x.id === gid) || {}).name); if (n) act({action: 'group_rename', group: gid, name: n}); return; }
    if (gact === 'delete') { if (confirm('Delete this group? Its motifs stay, ungrouped.')) act({action: 'group_delete', group: gid}); return; }
    if (gid === '+') { const n = prompt('Name the new group (a chapter, e.g. "the enemy within")'); if (n) act({action: 'group_add', name: n}); return; }
    if (gid === 'newmotif') return;  // a drop zone for dragged claims
    filter = gid; render(); return;
  }
  if (!m) return;
  const e = data.entries.find((x) => x.id === m.dataset.id);
  if (ev.target.closest('[data-more]')) { expanded.has(e.id) ? expanded.delete(e.id) : expanded.add(e.id); render(); return; }
  const li = ev.target.closest('li');
  if (li && !ev.target.closest('button')) { if (!justDragged) openPicker(li.dataset.claim, e.id); return; }
  if (b && li) {
    if (b.dataset.cact === 'out' && confirm('Take this claim out of “' + e.name + '” for good?')) act({action: 'unfile', claim: li.dataset.claim, id: e.id});
    return;
  }
  if (b && b.dataset.unrelate) { act({action: 'unrelate', a: e.id, b: b.dataset.unrelate}); return; }
  if (b && b.dataset.mact) {
    const a = b.dataset.mact;
    if (a === 'more') openSimilar(e.id);
    else if (a === 'unparent') act({action: 'parent', id: e.id, parent: null});
    else if (a === 'rename') { const n = prompt('Rename the motif', e.name); if (n) act({action: 'rename', id: e.id, name: n}); }
    else if (a === 'ungroup') act({action: 'group_assign', id: e.id, group: null});
    else if (a === 'done' || a === 'undone') act({action: 'done', id: e.id, done: a === 'done'});
    else if (a === 'delete' && confirm(`Delete “${e.name}”? Its ${e.claims.length} claims keep their other motifs and aren't filed here again.`)) act({action: 'delete', id: e.id});
    return;
  }
});
// Click a claim: its motifs now, and every other motif to move it to or file it under as well
let pick = null;
function openPicker(claim, from) { pick = {claim, from}; $('#picker').showModal(); drawPicker(''); }
function drawPicker(q) {
  const {claim, from} = pick, lower = q.trim().toLowerCase();
  const mine = data.entries.filter((e) => e.claims.some((c) => c.claim === claim));
  let others = data.entries.filter((e) => !mine.includes(e) && (!lower || e.name.toLowerCase().includes(lower)
    || e.claims.some((c) => c.claim.toLowerCase().includes(lower))));
  others.sort((a, b) => (lower ? (b.name.toLowerCase().includes(lower) - a.name.toLowerCase().includes(lower)) : 0) || b.claims.length - a.claims.length);
  // A person curating isn't held to the model's three motifs a claim: adding is always on offer
  const fromName = esc((data.entries.find((e) => e.id === from) || {}).name || 'this motif');
  // What's typed, when no motif has that name: a new motif, first in the list (even when other motifs partly match; Enter adds it when none do)
  const typed = q.trim(), taken = data.entries.some((e) => e.name.toLowerCase() === typed.toLowerCase());
  const newRow = typed && !taken ? `<div class="newfromq"><span class="nm">✨ “${esc(typed)}”</span><span class="ct">new</span>
    <button class="small add" data-alsonew="1" title="make a new motif with this name and file the claim under it too">+ add as a new motif</button>
    <button class="small" data-movenew="1" title="make it and put it in place of “${fromName}”">replace “${fromName}”</button></div>` : '';
  $('#picker-body').innerHTML = `<h2>${esc(claim)}</h2>
    <div class="now">Filed under: ${mine.map((e) => `<span>🧩 ${esc(e.name)} <button class="small" data-out="${e.id}" title="take this motif off this claim">✗</button> <button class="small" data-del="${e.id}" title="delete this whole motif (${e.claims.length} claim${e.claims.length === 1 ? '' : 's'})">🗑</button></span>`).join('')}</div>
    <input type="search" id="pick-q" placeholder="find a motif by name or claim" value="${esc(q)}" style="width:100%;padding:5px 10px;border:2px solid #1f1f2e;border-radius:999px">
    <div class="pick">${newRow}${others.slice(0, 40).map((e) => `<div><span class="nm">🧩 ${esc(e.name)}</span><span class="ct">${e.claims.length}</span>
      <button class="small add" data-also="${e.id}" title="file the claim under this motif too, keeping the others">+ add</button>
      <button class="small" data-move="${e.id}" title="put this motif in place of “${fromName}”">replace “${fromName}”</button></div>`).join('') || (newRow ? '' : '<p>No motif matches.</p>')}</div>`;
  const input = $('#pick-q'); input.focus(); input.setSelectionRange(q.length, q.length);
  input.addEventListener('input', () => drawPicker(input.value));
  input.addEventListener('keydown', (ev) => { const add = $('.pick [data-alsonew]');
    if (ev.key === 'Enter' && add && !$('.pick [data-also]')) { ev.preventDefault(); add.click(); } });
}
$('#picker').addEventListener('click', (ev) => {
  const b = ev.target.closest('button'), {claim, from} = pick || {};
  if (ev.target === $('#picker') || (b && b.dataset.close)) { $('#picker').close(); return; }
  if (!b) return;
  const name = ($('#pick-q') || {}).value || '';
  // The picker stays open after each change, redrawn, so several can be made in a row (it closed after one)
  const done = async (body) => {
    const q = ($('#pick-q') || {}).value || '';
    await act(body);
    const holders = data.entries.filter((e) => e.claims.some((c) => c.claim === claim));
    if (!holders.length) { $('#picker').close(); return; }  // its last motif gone: it's filed again next run
    if (!holders.some((e) => e.id === pick.from)) pick.from = holders[0].id;
    drawPicker(q);
  };
  const mine = data.entries.filter((e) => e.claims.some((c) => c.claim === claim)).length;
  if (b.dataset.move) done({action: 'move', claim, source: from, target: b.dataset.move});
  else if (b.dataset.also) done({action: 'also', claim, source: from, target: b.dataset.also});
  else if (b.dataset.out && (mine > 1 || confirm('That\'s its last motif: take it off, and it\'s filed again next run?')))
    done({action: 'unfile', claim, id: b.dataset.out});
  else if (b.dataset.del) {
    const e = data.entries.find((x) => x.id === b.dataset.del);
    if (confirm(`Delete the motif “${e.name}” (${e.claims.length} claim${e.claims.length === 1 ? '' : 's'})? Its claims keep their other motifs and aren't filed under it again.`))
      done({action: 'delete', id: e.id});
  }
  else if (b.dataset.movenew && name.trim()) done({action: 'move_new', claim, source: from, name});
  else if (b.dataset.alsonew && name.trim()) done({action: 'also_new', claim, source: from, name});
});

// Click and drag (mouse, pen or touch): a claim onto a motif adds it there (with a one-click 'take it out of' the old
// one), a motif onto a motif merges them, a motif onto a group files it, a claim onto '+ new motif' starts one.
// A press without movement is a click. On touch, hold a moment before dragging, so a swipe still scrolls.
let drag = null, justDragged = false;
const ghost = document.createElement('div');
ghost.className = 'ghost'; document.body.appendChild(ghost);
function targetAt(x, y) {
  const el = document.elementFromPoint(x, y);
  return el && el.closest('.motif, .group');
}
function mark(t) { document.querySelectorAll('.target').forEach((x) => x !== t && x.classList.remove('target')); if (t) t.classList.add('target'); }
function startDrag() {
  drag.on = true; document.body.classList.add('dragging');
  ghost.textContent = drag.item.type === 'claim' ? '🧩 ' + drag.item.claim.slice(0, 70) : '🧩 ' + drag.item.name;
  ghost.style.display = 'block'; moveGhost(drag.x, drag.y); scrollLoop();
}
function moveGhost(x, y) { ghost.style.left = (x + 12) + 'px'; ghost.style.top = (y + 12) + 'px'; }
function scrollLoop() {  // near the window's top or bottom edge, the page scrolls so far cards can be reached
  if (!drag || !drag.on) return;
  const edge = 80, y = drag.y;
  const speed = y < edge ? -(edge - y) / 3 : y > innerHeight - edge ? (y - (innerHeight - edge)) / 3 : 0;
  if (speed) { scrollBy(0, speed); mark(targetAt(drag.x, drag.y)); }
  requestAnimationFrame(scrollLoop);
}
document.addEventListener('pointerdown', (ev) => {
  if (ev.button !== 0 || ev.target.closest('button, input, select, a, dialog')) return;
  const li = ev.target.closest('.motif li[data-claim]'), head = ev.target.closest('.motif .head'), m = ev.target.closest('.motif');
  if (!m || (!li && !head)) return;
  const e = data.entries.find((x) => x.id === m.dataset.id);
  const item = li ? {type: 'claim', claim: li.dataset.claim, from: e.id, fromName: e.name} : {type: 'motif', id: e.id, name: e.name};
  drag = {item, x: ev.clientX, y: ev.clientY, sx: ev.clientX, sy: ev.clientY, on: false, touch: ev.pointerType === 'touch'};
  if (drag.touch) drag.timer = setTimeout(() => { if (drag && !drag.on) startDrag(); }, 350);
});
document.addEventListener('pointermove', (ev) => {
  if (!drag) return;
  drag.x = ev.clientX; drag.y = ev.clientY;
  const moved = Math.hypot(ev.clientX - drag.sx, ev.clientY - drag.sy);
  if (!drag.on) {
    if (drag.touch) { if (moved > 8) { clearTimeout(drag.timer); drag = null; } return; }  // a swipe: let it scroll
    if (moved < 6) return;
    startDrag();
  }
  ev.preventDefault(); moveGhost(ev.clientX, ev.clientY); mark(targetAt(ev.clientX, ev.clientY));
});
document.addEventListener('touchmove', (ev) => { if (drag && drag.on) ev.preventDefault(); }, {passive: false});
function endDrag(ev, cancel) {
  if (!drag) return;
  clearTimeout(drag.timer);
  const d = drag; drag = null;
  ghost.style.display = 'none'; document.body.classList.remove('dragging'); mark(null);
  if (!d.on) return;
  justDragged = true; setTimeout(() => { justDragged = false; }, 0);
  if (cancel) return;
  const t = targetAt(ev.clientX, ev.clientY);
  if (t) dropOn(d.item, t);
}
document.addEventListener('pointerup', (ev) => endDrag(ev, false));
document.addEventListener('pointercancel', (ev) => endDrag(ev, true));
addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && drag) endDrag(ev, true); });
async function dropOn(item, t) {
  if (t.classList.contains('motif')) {
    const target = data.entries.find((x) => x.id === t.dataset.id);
    if (item.type === 'claim') {
      if (target.id === item.from || target.claims.some((c) => c.claim === item.claim)) return;
      await act({action: 'also', claim: item.claim, source: item.from, target: target.id});
      toast(`Added to “${target.name}”.`, [[`also take it out of “${item.fromName}”`, () => act({action: 'unfile', claim: item.claim, id: item.from})]]);
    } else if (item.id !== target.id) {
      chooseMotifDrop(item, target);
    }
    return;
  }
  const g = t.dataset.g;
  if (g === 'newmotif' && item.type === 'claim') {
    const n = prompt('Name the new motif'); if (n) act({action: 'also_new', claim: item.claim, source: item.from, name: n});
  } else if (item.type === 'motif' && (g.startsWith('G') || g === 'none')) {
    act({action: 'group_assign', id: item.id, group: g === 'none' ? null : g});
  }
}
// '＋ more like this': the claims closest to a motif; each add or 'not this' recomputes the list from the motif's claims
let simFor = null;
async function openSimilar(id) { simFor = id; $('#similar').showModal(); await drawSimilar(); }
async function drawSimilar() {
  const e = data.entries.find((x) => x.id === simFor);
  if (!e) { $('#similar').close(); return; }
  $('#similar-body').innerHTML = `<h2>More like 🧩 ${esc(e.name)} <span class="meta">(${e.claims.length} claim${e.claims.length === 1 ? '' : 's'})</span></h2><p class="meta">Finding the closest claims…</p>`;
  const r = await fetch('/motif-similar.json?id=' + encodeURIComponent(simFor));
  const items = r.ok ? await r.json() : [];
  $('#similar-body').innerHTML = `<h2>More like 🧩 ${esc(e.name)} <span class="meta">(${e.claims.length} claim${e.claims.length === 1 ? '' : 's'})</span></h2>
    <p class="meta">Closest first. Each choice reshuffles the list around the motif's claims.</p>
    <div class="pick">${items.map((i, n) => `<div class="simrow"><span class="nm">${esc(i.claim)}
      <span class="meta">${esc(i.source === 'narrative' ? 'online' : i.source)} · now in ${i.motifs.map((m) => esc(m.name)).join(', ')}</span></span>
      <span class="ct" title="how close, 0 to 1">${i.score.toFixed(2)}</span>
      <button class="small add" data-simadd="${n}">+ add</button><button class="small" data-simno="${n}" title="not this motif: never suggested or filed here">✗ not this</button></div>`).join('')
      || '<p>No other claims to suggest.</p>'}</div>`;
  $('#similar-body').items = items;
}
$('#similar').addEventListener('click', async (ev) => {
  const b = ev.target.closest('button');
  if (ev.target === $('#similar') || (b && b.dataset.close)) { $('#similar').close(); return; }
  if (!b) return;
  const items = $('#similar-body').items || [];
  const i = items[+(b.dataset.simadd ?? b.dataset.simno)];
  if (!i) return;
  b.closest('.simrow').style.opacity = .4;
  if (b.dataset.simadd !== undefined) await act({action: 'also', claim: i.claim, source: i.motifs[0].id, target: simFor});
  else await act({action: 'reject', claim: i.claim, id: simFor});
  drawSimilar();
});

// A motif dropped on another: merge them, or make it a kind of the other
function chooseMotifDrop(item, target) {
  $('#choose-body').innerHTML = `<h2>🧩 ${esc(item.name)} → 🧩 ${esc(target.name)}</h2>
    <p><button class="add" data-c="kind">⊂ “${esc(item.name)}” is a kind of “${esc(target.name)}”</button></p>
    <p><button data-c="related">↔ related: near each other, but different stories</button></p>
    <p><button data-c="merge">⤵ merge them: “${esc(item.name)}” joins “${esc(target.name)}” (its name goes)</button></p>
    <p><button data-c="cancel">cancel</button></p>`;
  $('#choose').onclick = (ev) => {
    const b = ev.target.closest('button'); if (!b && ev.target !== $('#choose')) return;
    $('#choose').close();
    if (b && b.dataset.c === 'kind') act({action: 'parent', id: item.id, parent: target.id});
    else if (b && b.dataset.c === 'merge') act({action: 'merge', source: item.id, target: target.id});
    else if (b && b.dataset.c === 'related') act({action: 'relate', a: item.id, b: target.id});
  };
  $('#choose').showModal();
}

let toastTimer;
function toast(text, buttons) {
  const box = $('#toast');
  box.innerHTML = esc(text) + ' ' + buttons.map(([label], i) => `<button class="small" data-t="${i}">${esc(label)}</button>`).join(' ');
  box.style.display = 'block';
  box.onclick = (ev) => { const b = ev.target.closest('button'); if (b) { buttons[+b.dataset.t][1](); box.style.display = 'none'; } };
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.style.display = 'none'; }, 9000);
}
$('#reset-done').addEventListener('click', () => { if (confirm('Bring back every motif marked done?')) act({action: 'reset_done'}); });
$('#add-motif').addEventListener('click', () => { const n = prompt('Name the new motif (claims can be moved into it)'); if (n) act({action: 'add', name: n}); });
['#q', '#sort', '#multi', '#showdone'].forEach((s) => $(s).addEventListener('input', render));
fetch('/motif-board.json').then((r) => r.json()).then((d) => { data = d; render(); });
</script></body></html>"""


EMPTY_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Empty motifs</title><style>
body { font-family: system-ui, sans-serif; background: #fffdf6; color: #1f1f2e; margin: 0 auto; max-width: 760px; padding: 16px; }
nav a { margin-right: 1em; } .row { display: flex; gap: 8px; align-items: center; padding: 6px 4px; border-bottom: 1px dashed #ccc; }
.row .nm { flex: 1; } .meta { color: #666; font-size: .85em; }
button { font: inherit; font-size: .9em; border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 3px 10px; cursor: pointer; }
</style></head><body>
<nav><a href="/">Label check</a> <a href="/motifs">Motif check</a> <a href="/motif-index">Motif organizer</a> <a href="/motif-board">Motif board</a> <b>Empty motifs</b> <a href="/entities">Names</a></nav>
<h1>Empty motifs</h1>
<p>Motifs with no claims: ones you made and never filled, or emptied by moving their claims out. Delete the ones you don't
want. Deleting one changes nothing else.</p>
<p><label><input type="checkbox" id="all"> select all</label> <button id="del-sel">🗑 delete selected</button></p>
<div id="list"></div>
<script>
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
let data = {entries: []};
// A motif with kinds under it can be empty on purpose (a 'Blame' over its kinds)
const empty = () => data.entries.filter((e) => !e.claims.length && !data.entries.some((x) => x.parent === e.id));
function render() {
  const list = empty();
  document.getElementById('list').innerHTML = list.map((e) => `<div class="row"><input type="checkbox" data-id="${e.id}">
    <span class="nm">🧩 ${esc(e.name)} <span class="meta">${e.id} · since ${esc(e.first_seen)}${e.curated ? ' · made by hand' : ''}</span></span>
    <button data-del="${e.id}">🗑 delete</button></div>`).join('') || '<p>No empty motifs. 🎉</p>';
}
async function del(ids) {
  for (const id of ids) {
    const r = await fetch('/motif-board', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'delete', id})});
    if (r.ok) data = await r.json(); else { alert('Failed: ' + await r.text()); break; }
  }
  render();
}
document.addEventListener('click', (ev) => { const b = ev.target.closest('[data-del]'); if (b) del([b.dataset.del]); });
document.getElementById('all').addEventListener('change', (ev) => document.querySelectorAll('#list input').forEach((c) => c.checked = ev.target.checked));
document.getElementById('del-sel').addEventListener('click', () => {
  const ids = [...document.querySelectorAll('#list input:checked')].map((c) => c.dataset.id);
  if (ids.length && confirm(`Delete ${ids.length} empty motif${ids.length === 1 ? '' : 's'}?`)) del(ids);
});
fetch('/motif-board.json').then((r) => r.json()).then((d) => { data = d; render(); });
</script></body></html>"""


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


def log_curation(page: str, data: dict, before: dict):
    os.makedirs(FOLDER, exist_ok=True)
    with open(CURATION_LOG, 'a') as f:
        f.write(json.dumps({'at': dt.now().isoformat(timespec='seconds'), 'page': page, 'action': data, 'before': before}) + '\n')


# Undo: each change on the organizer pages snapshots the file it touched (the motif index, or the name aliases) so the
# last ones can be stepped back, newest first. Kept on disk, so a server restart doesn't lose them.
UNDO = os.path.join(FOLDER, 'undo')
UNDO_KEEP = 50


def undo_paths() -> dict:
    from app.analysis import entities, motif_index
    return {'/motif-board': motif_index.INDEX, '/motif-index': motif_index.INDEX, '/motif-verdict': motif_index.INDEX,
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
    parts = [act] + [f'“{name(k)}”' for k in ('source', 'id', 'a', 'child') if data.get(k)]
    parts += [f'→ “{name(k)}”' for k in ('target', 'b', 'parent') if data.get(k)]
    if data.get('name'):
        parts.append(f'as “{data["name"]}”')
    return ' '.join(parts)[:160]


def push_undo(path: str, before_text: str | None, what: str):
    after = read_text(path)
    if after == before_text:
        return
    os.makedirs(UNDO, exist_ok=True)
    stamp = dt.now().strftime('%Y%m%d-%H%M%S-%f')
    with open(os.path.join(UNDO, stamp + '.json'), 'w') as f:
        json.dump({'path': path, 'before': before_text, 'after_sha': hashlib.sha1((after or '').encode()).hexdigest(),
                   'what': what, 'at': stamp}, f)
    for old in sorted(os.listdir(UNDO))[:-UNDO_KEEP]:
        os.remove(os.path.join(UNDO, old))


def last_undo() -> tuple[str, dict] | None:
    try:
        names = sorted(n for n in os.listdir(UNDO) if n.endswith('.json'))
    except OSError:
        return None
    if not names:
        return None
    path = os.path.join(UNDO, names[-1])
    with open(path) as f:
        return path, json.load(f)


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
    log_curation('undo', {'action': 'undo', 'undid': snap['what']}, {})
    return snap['what']


UNDO_SNIPPET = """<script>
(function () {
  const b = document.getElementById('undo-btn'), w = document.getElementById('undo-what');
  if (!b) return;
  async function state() {
    const d = await (await fetch('/undo.json')).json();
    b.disabled = !d.what; w.textContent = d.what ? 'undo: ' + d.what : '';
  }
  async function undo() {
    if (b.disabled) return;
    const r = await fetch('/undo', {method: 'POST'});
    if (!r.ok) { alert('Can\u2019t undo: ' + await r.text()); return; }
    location.reload();
  }
  b.addEventListener('click', undo);
  addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.target.closest('input, textarea')) { e.preventDefault(); undo(); } });
  window.refreshUndo = state; state();
})();
</script>"""
UNDO_BUTTON = ' <button id="undo-btn" disabled title="undo your last change (Ctrl+Z)">↶ undo</button> <span id="undo-what" style="font-size:.8em;color:#555"></span></nav>'


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
    elif act in ('relate', 'unrelate') and data.get('a') in live and data.get('b') in live:
        mi.relate(data['a'], data['b'], act == 'relate')
    elif act == 'parent' and data.get('id') in live and (data.get('parent') is None or data.get('parent') in live):
        mi.set_parent(data['id'], data.get('parent'))
    elif act == 'reject' and text('claim') and data.get('id') in live:
        mi.reject(data['claim'], data['id'])
    elif act == 'done' and data.get('id') in live:
        mi.mark_done(data['id'], bool(data.get('done', True)))
    elif act == 'reset_done':
        mi.reset_done()
    elif act == 'group_add' and text('name'):
        mi.group_add(data['name'])
    elif act == 'group_rename' and data.get('group') in index.get('groups', {}) and text('name'):
        mi.group_rename(data['group'], data['name'])
    elif act == 'group_delete' and data.get('group') in index.get('groups', {}):
        mi.group_delete(data['group'])
    elif act == 'group_assign' and data.get('id') in live:
        mi.group_assign(data['id'], data.get('group') or None)
    elif act in ('rename', 'merge', 'delete', 'add'):
        organizer_action(data)
    else:
        raise ValueError(f'unknown action: {data}')


def entities_page() -> str:
    """The names organizer (#165): one name per subject for the 'mentioned:' filters. Suggested merges first (a name
    inside another), then every subject with the names that point to it."""
    from app.analysis import entities
    esc = html.escape
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
    suggest = ''.join(f"""
<section class="card pair">
  <p class="outlet">one name inside the other</p>
  <div class="two"><div><b>{esc(a)}</b> <span class="said">{subjects.get(a, {}).get('stories', 0)} stories</span></div>
    <div><b>{esc(b)}</b> <span class="said">{subjects.get(b, {}).get('stories', 0)} stories</span></div></div>
  <div class="row"><button data-act="merge" data-source="{esc(a)}" data-target="{esc(b)}">⤵ “{esc(a)}” is “{esc(b)}”</button>
    <button data-act="merge" data-source="{esc(b)}" data-target="{esc(a)}">⤵ “{esc(b)}” is “{esc(a)}”</button>
    <button data-act="not_same" data-a="{esc(a)}" data-b="{esc(b)}">✗ different subjects</button></div>
</section>""" for a, b in pairs[:40])
    rows = sorted(subjects.items(), key=lambda kv: (-kv[1]['stories'], kv[0].lower()))
    cards = ''.join(f"""
<section class="card entry" data-text="{esc((name + ' ' + ' '.join(e['names'])).lower())}">
  <p class="outlet">{e['stories']} stor{'y' if e['stories'] == 1 else 'ies'}</p>
  <div class="row"><input class="name" value="{esc(name)}" size="40"><button data-act="rename" data-source="{esc(name)}">rename</button>
    <button data-act="merge_into" data-source="{esc(name)}">⤵ another name for…</button></div>
  {'<p class="said">also named: ' + ' '.join(f'{esc(n)} <button class="small" data-act="unmerge" data-name="{esc(n)}">✗ not this</button>' for n in sorted(e['names'])) + '</p>' if e['names'] else ''}
</section>""" for name, e in rows)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Names</title><style>
body {{ font-family: system-ui, sans-serif; background: #fffdf6; color: #1f1f2e; margin: 0 auto; max-width: 900px; padding: 16px; }}
.card {{ border: 2px solid #1f1f2e; border-radius: 12px; padding: 8px 14px; margin: 10px 0; background: #fff; box-shadow: 4px 4px 0 #00c2a8; }}
.pair {{ box-shadow: 4px 4px 0 #ff4fa3; }} .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.outlet, .said {{ font-size: .85em; color: #555; }} p {{ margin: .3em 0; }}
.row {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: .4em 0; }} input {{ font: inherit; padding: 3px 6px; }}
button {{ font: inherit; font-size: .85em; border: 1.5px solid #1f1f2e; border-radius: 999px; background: #fff; padding: 3px 10px; cursor: pointer; }}
button.small {{ font-size: .75em; padding: 1px 7px; }} nav a {{ margin-right: 1em; }} h2 {{ margin-top: 1.4em; }}
@media (max-width: 640px) {{ .two {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<nav><a href="/">Label check</a> <a href="/motifs">Motif check</a> <a href="/motif-index">Motif organizer</a> <a href="/motif-board">Motif board</a> <b>Names</b></nav>
<h1>Names</h1>
<p>The people, places and groups the local model names in each story, for the “mentioned:” filters on the front page:
{len(subjects)} subjects under {len(counts)} names. Give each subject one name: merge names for the same subject, rename
a subject, or keep two apart. Changes go live with the next site build.</p>
<h2>Suggested merges</h2>
{suggest or '<p>No suggestions right now.</p>'}
<h2>Every subject</h2>
<p><input type="search" id="search" placeholder="search names" size="40"></p>
{cards}
<script>
const post = async (body) => {{
  const r = await fetch('/entities', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)}});
  if (!r.ok) {{ alert('Failed: ' + await r.text()); return; }}
  const y = scrollY; location.reload(); setTimeout(() => scrollTo(0, y), 50);
}};
document.addEventListener('click', (ev) => {{
  const b = ev.target.closest('button[data-act]');
  if (!b) return;
  const d = b.dataset;
  if (d.act === 'merge') post({{action: 'merge', source: d.source, target: d.target}});
  else if (d.act === 'not_same') post({{action: 'not_same', a: d.a, b: d.b}});
  else if (d.act === 'rename') post({{action: 'merge', source: d.source, target: b.previousElementSibling.value.trim()}});
  else if (d.act === 'merge_into') {{ const t = prompt('“' + d.source + '” is another name for which subject?'); if (t && t.trim()) post({{action: 'merge', source: d.source, target: t.trim()}}); }}
  else if (d.act === 'unmerge') post({{action: 'unmerge', name: d.name}});
}});
document.getElementById('search').addEventListener('input', (ev) => {{
  const q = ev.target.value.trim().toLowerCase();
  document.querySelectorAll('.entry').forEach((c) => {{ c.hidden = q && !c.dataset.text.includes(q); }});
}});
</script></body></html>"""


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
        if self.path.startswith('/undo.json'):
            found = last_undo()
            return self.send_json({'what': found[1]['what'] if found else None})
        if self.path.startswith('/motif-similar.json'):
            from urllib.parse import urlparse, parse_qs
            from app.analysis import motif_index
            eid = parse_qs(urlparse(self.path).query).get('id', [''])[0]
            if eid not in {e['id'] for e in motif_index.live(motif_index.load())}:
                self.send_error(404)
                return
            return self.send_json(motif_index.similar(eid))
        if self.path.startswith('/motif-board.json'):
            from app.analysis import motif_index
            return self.send_json(motif_index.board())
        body = (EMPTY_PAGE if self.path.startswith('/motif-empty') else BOARD_PAGE if self.path.startswith('/motif-board') else organizer_page() if self.path.startswith('/motif-index') else motif_page()
                if self.path.startswith('/motifs') else entities_page() if self.path.startswith('/entities')
                else page())
        if self.path.split('?')[0] != '/':  # every organizer page gets the undo button (the label check writes the database)
            body = body.replace('</nav>', UNDO_BUTTON, 1).replace('</body>', UNDO_SNIPPET + '</body>', 1)
        body = body.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')  # a page changed under an open tab shows on reload, never stale
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def remember(self, data: dict, before: dict):
        if getattr(self, '_undo', None):
            push_undo(self._undo[0], self._undo[1], describe(data, before))

    def send_json(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
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
        undo_path = undo_paths().get(self.path)
        self._undo = (undo_path, read_text(undo_path)) if undo_path else None
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
