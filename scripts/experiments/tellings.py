"""A claim's tellings, for the experiments that give the models the tellers' own words (J2, W1; the casebook's lesson:
the person's rulings turn on what the tellers say, and the filing models see only the claim's one-line summary).
From the checker's 'where it came from' (validate.claim_detail): the focus-group quote, every show's quote, the
fact-check's summary and opening, or the posts that told it. Also how many distinct tellers (posters or shows; one
show across segments counts once: the praxis's repetition bar) and the share of them that are straight-news bulletins.
Cached by claim (TELLINGS)."""
import importlib.util
import json
import os
import sys

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

TELLINGS = os.path.join(Config.data, 'motifs', 'experiments', 'tellings.json')
MAX = 3  # tellings shown to a model
CHARS = 300
# Shows that report the day's news rather than comment on it (by name, as tellings carry them; Oct 9)
NEWS_SHOWS = {'Up First (NPR)', 'Reuters World News', 'BBC Global News Podcast', "WSJ What's News", 'Bloomberg News Now',
              'NPR News Now', 'ABC News Update', 'Top Story with Tom Llamas (NBC)', 'CNN 5 Things', 'Morning Wire',
              'Politico Playbook', 'The Intelligence (Economist)', 'The Daily (NYT)', 'Today in Focus (Guardian)',
              'The Take (Al Jazeera)', 'NPR Politics Podcast', 'Today, Explained'}
_V = None


def _validate():
    global _V
    if _V is None:
        spec = importlib.util.spec_from_file_location('validate', '/home/mas/Repos/maudlin2/scripts/validate.py')
        _V = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_V)
    return _V


def _short(t: str) -> str:
    t = ' '.join(str(t or '').split())
    return t if len(t) <= CHARS else t[:CHARS].rsplit(' ', 1)[0] + '…'


def gather(claim: str) -> dict:
    """{'kind', 'texts': the tellers' words (up to MAX), 'tellers': how many distinct, 'news': share by news shows}"""
    d = _validate().claim_detail(claim)
    kind = d.get('kind', '')
    if kind == 'focus-group':
        return {'kind': kind, 'texts': [_short(f'A voter in a focus group: "{d.get("quote") or ""}"')] if d.get('quote') else [],
                'tellers': 1, 'news': 0.0}
    if kind == 'radio & podcasts':
        told = d.get('tellings') or []
        shows = {t['show'] for t in told}
        texts, seen = [], set()
        for t in told:  # one per show first
            if t['show'] in seen or not t.get('quote'):
                continue
            seen.add(t['show'])
            who = {'host': 'its host', 'guest': 'a guest', 'caller': 'a caller', 'clip': 'a clip it played'}.get(t.get('speaker'), 'someone')
            texts.append(_short(f'{t["show"]}, {who}: "{t["quote"]}"'))
        return {'kind': kind, 'texts': texts[:MAX], 'tellers': len(shows),
                'news': sum(s in NEWS_SHOWS for s in shows) / max(len(shows), 1)}
    if kind == 'fact-check':
        texts = [_short(f'The fact-check: {d.get("title") or ""}. {d.get("summary") or ""}')]
        if d.get('piece'):
            texts.append(_short(d['piece']))
        return {'kind': kind, 'texts': texts, 'tellers': 1, 'news': 0.0}
    if kind == 'folklore':
        posts = [p['text'] for p in (d.get('all_posts') or []) if not p.get('reply')] or d.get('examples') or []
        return {'kind': kind, 'texts': [_short(f'A post: "{p}"') for p in posts[:MAX]],
                'tellers': int(d.get('people') or len(posts) or 0), 'news': 0.0}
    return {'kind': kind, 'texts': [], 'tellers': 0, 'news': 0.0}


def load() -> dict:
    try:
        with open(TELLINGS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def of(claims: list[str]) -> dict:
    """Each claim's tellings by its key, gathered once and cached"""
    saved = load()
    todo = [c for c in dict.fromkeys(claims) if mi.key(c) not in saved]
    for i, c in enumerate(todo):
        try:
            saved[mi.key(c)] = gather(c)
        except Exception as e:  # noqa: BLE001 - a claim whose source is gone has none
            saved[mi.key(c)] = {'kind': f'error: {type(e).__name__}', 'texts': [], 'tellers': 0, 'news': 0.0}
        if i % 50 == 49:
            json.dump(saved, open(TELLINGS, 'w'))
            print(f'tellings {i + 1}/{len(todo)}', flush=True)
    json.dump(saved, open(TELLINGS, 'w'))
    return {mi.key(c): saved[mi.key(c)] for c in claims}


def block(t: dict) -> str:
    """The tellings as lines for a model"""
    return '\n'.join(f'- {x}' for x in t.get('texts', [])) or '(no tellings kept)'


if __name__ == '__main__':
    from collections import Counter
    from app.analysis import filing_confidence as fc
    claims = [c for c, *_ in fc.labeled(mi.load())]
    got = of(claims)
    print(len(got), Counter(t['kind'] for t in got.values()), sum(1 for t in got.values() if t['texts']))
