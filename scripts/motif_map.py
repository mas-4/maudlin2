"""The person's own motif map (Oct 30; the person: "it would be cool to have a way to just visualize embedding space of
these motif systems"): the public motif space page (motif-space.html) with nothing held back: every live motif, done
or not, every filing, checked or not, and the filing's own space (mxbai) beside meaning and words. Laid out by
app/analysis/motif_space.py from the embedding cache (no model asked, about a minute on the CPU), drawn by the site's
own script, markup and styles, all inlined into one file to open or publish privately. Never for the public site: it
holds unchecked filings and claims the accusations screen would hold.

    motif_map.py OUT_DIR      writes OUT_DIR/index.html"""
import json
import os
import sys
from datetime import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_space  # noqa: E402

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'site')


def lit(v):
    """A field as saved: some copies keep lists and dicts as their Python text"""
    if isinstance(v, str) and v[:1] in '[{':
        import ast
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    return v


def entries(index: dict) -> list[dict]:
    out = []
    for e in mi.live(index):
        claims = [c for c in (lit(e.get('claims')) or []) if isinstance(c, dict) and c.get('claim')]
        if not claims:
            continue
        facets = lit(e.get('facets'))
        out.append({'id': e['id'], 'name': e['name'], 'note': e.get('note') or '',
                    'genre': facets.get('genre') if isinstance(facets, dict) else None,
                    'groups': list(lit(e.get('groups')) or []), 'rests': list(lit(e.get('parents')) or []),
                    'done': bool(lit(e.get('done'))),
                    'claims': [{'text': c['claim'], 'shown': c['claim'], 'ok': c.get('checked') == 'yes'} for c in claims]})
    return out


def read(*parts) -> str:
    with open(os.path.join(SITE, *parts), encoding='utf-8') as f:
        return f.read()


def build(out: str):
    index = mi.load()
    data = motif_space.layout(entries(index), tuple(motif_space.SPACES))
    at = {m['id']: i for i, m in enumerate(data['motifs'])}
    for m in data['motifs']:
        m['rests'] = [at[p] for p in m['rests'] if p in at]
    data.update({'public': False, 'groups': {g: v.get('name', g) for g, v in index.get('groups', {}).items()},
                 'genres': mi.facet_values(index).get('genre', []),
                 'related': [[at[a], at[b]] for a, b in (tuple(p) for p in index.get('related', []) if len(p) == 2)
                             if a in at and b in at]})
    for c in data['claims']:
        c.pop('k', None)
    page = f"""<meta charset="utf-8">
<title>Motif Map</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bungee&family=Comic+Neue:wght@700&display=swap">
<style>
:root {{ color-scheme: light; }}
html, body {{ background: #fff; color: #1f1f2e; }}
body {{ font: 15px/1.5 Helvetica, Arial, sans-serif; padding-block: 18px 48px;
    padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
.wrap {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ font: 24px/1 'Bungee', sans-serif; display: inline-block; background: #00c2a8; border: 3px solid #1f1f2e;
    border-radius: 999px; padding: 8px 16px 6px; box-shadow: 4px 4px 0 #1f1f2e; transform: rotate(-2deg); margin: 0 0 8px; }}
.lede {{ font: 700 15px/1.4 'Comic Neue', 'Comic Sans MS', cursive; margin: 6px 0; }}
{read('styles', '780-motif-space.css')}
</style>
<div class="wrap">
<h1>🗺️ Motif map</h1>
<p class="lede">Every live motif and filing, checked or not: {len(data['motifs']):,} motifs, {len(data['claims']):,} claims.
The private copy of the site's motif space page, built {dt.now():%b %-d, %H:%M}.</p>
{read('templates', 'motif_space_markup.html')}
</div>
<script id="ms-data" type="application/json">{json.dumps(data, separators=(',', ':')).replace('</', '<\\/')}</script>
<script>{read('static', 'motif_space.js')}</script>
"""
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page)
    print(f'wrote {out}/index.html ({os.path.getsize(os.path.join(out, "index.html")) / 1e6:.1f} MB)')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
