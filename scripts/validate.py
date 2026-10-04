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
                'spice': int(loaded), 'feelings': [e for e in (ranks or '').split(',') if e in FEELINGS][:2],
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
<h1>Label check</h1>
<p>Is the model right? Tap ✓ for a label that's right, or the value it should be (dashed: the model's pick). Feelings
take one or two. Save each card; reload for more.</p>
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
      if (picked.length) verdict.feelings = {{ok: false, should: picked}}; else delete verdict.feelings;
    }} else {{
      card.querySelectorAll(`[data-measure="${{m}}"]`).forEach((x) => x.classList.toggle('chosen', x === b));
      verdict[m] = {{ok: false, should: Number(b.dataset.value)}};
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = page().encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/verdict':
            self.send_error(404)
            return
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
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
