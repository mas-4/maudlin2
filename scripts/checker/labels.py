"""The headline label check (#121), the page the checker began as: the language model's mood, spice (loaded wording)
and feelings for headlines, marked right or corrected by eye. A correction goes straight onto the headline as its hand
labels; verdicts are appended to data/validation/verdicts.jsonl (one line per headline, with the model's labels at the
time), and the page's footer keeps a running agreement count. Headlines are drawn from the last two days, spread evenly
over the model's mood and spice values so the rare ones (very grim, very loaded) get checked as often as the common
ones. Moved out of scripts/validate.py on Oct 21 (Fable's architecture review); served at / as before."""
import json
import os
import random
from collections import Counter
from datetime import datetime as dt, timedelta as td

from app.analysis.newsfilter import EMOTIONS, EMOTION_EMOJI
from app.models import Session, Headline, Article, Agency
from app.utils import Config

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


def state() -> dict:
    """What the page shows: a batch of headlines, the running agreement, and the choices for each measure. The old
    page renders it; the React app reads it as /labels.json (in JSON, the moods' and spices' keys become strings)."""
    return {'items': batch(), 'stats': stats(), 'moods': MOODS, 'spices': SPICES, 'feelings': FEELINGS,
            'emoji': EMOTION_EMOJI}


def page(render) -> str:
    s = state()
    items, st = s['items'], s['stats']
    for it in items:
        it['model_json'] = json.dumps({k: it[k] for k in ('mood', 'spice', 'feelings')})
    pct = lambda k: f"{100 * st[k][0] / st[k][1]:.0f}% of {st[k][1]}" if st[k][1] else '—'  # noqa: E731
    return render('label.html', '/', undo=False, items=items, st=st, pct=pct, moods=s['moods'], spices=s['spices'],
                  feelings=s['feelings'], emoji=s['emoji'])




def record(data: dict):
    """A verdict: onto the headline, and into the file for agreement scores"""
    apply_label(data)
    data['at'] = dt.now().isoformat(timespec='seconds')
    os.makedirs(FOLDER, exist_ok=True)
    with open(VERDICTS, 'a') as f:
        f.write(json.dumps(data) + '\n')
