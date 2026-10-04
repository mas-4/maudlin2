"""Each side's wording on a story: the two-word phrases that outlets on one side of the lean scale put in their headlines
and no outlet on the other side does. On the FlyDubai cockpit attack, left-leaning outlets wrote "extremism concerns"
and "terrorist act" while right-leaning ones wrote "hero pilot" and "FlyDubai hijacker"; on the senator's phone
number, "Trump urges" against "Trump doxes". Word choice in plain sight, with no model involved.

Our outlets lean left as a group, so a phrase only the left uses is less telling than one only the right uses unless
both sides are well represented: a story needs MIN_SIDE rated outlets on each side, and a phrase needs MIN_OUTLETS
outlets and MIN_SHARE of its side's outlets, with none on the other side."""
import re
from collections import defaultdict

from nltk.corpus import stopwords

MIN_SIDE = 3
MIN_OUTLETS = 2
MIN_SHARE = 0.25
SHOWN = 3
WORD = re.compile(r"[a-z0-9][a-z0-9'’-]*[a-z0-9]|[a-z0-9]")
# Words that make a phrase say nothing about framing: function words, and the filler of headline grammar
FILLER = set(stopwords.words('english')) | {
    'says', 'say', 'said', 'new', 'us', 'u.s', 'report', 'reports', 'amid', 'could', 'would', 'may', 'video',
    'watch', 'live', 'update', 'updates', 'news', 'latest', 'per', 'via', 'gets', 'get', 'set', 'one', 'two',
}


def bigrams(title: str) -> set[str]:
    words = WORD.findall(title.lower().replace('’', "'"))
    return {f'{a} {b}' for a, b in zip(words, words[1:]) if a not in FILLER and b not in FILLER}


def side(row: dict) -> str | None:
    if not row.get('rated'):
        return None
    return 'left' if row['bias'] < 0 else 'right' if row['bias'] > 0 else None


def joined(phrases: list[dict]) -> list[dict]:
    """Phrases the same outlets used back to back joined into one: "small texas" and "texas town" from the same
    outlets read "small texas town"."""
    phrases = sorted(phrases, key=lambda p: p['phrase'])
    merged = True
    while merged:
        merged = False
        for a in phrases:
            for b in phrases:
                if a is not b and a['outlets'] == b['outlets'] and a['phrase'].split()[-1] == b['phrase'].split()[0] \
                        and b['phrase'] not in a['phrase']:
                    a['phrase'] += ' ' + ' '.join(b['phrase'].split()[1:])
                    phrases.remove(b)
                    merged = True
                    break
            if merged:
                break
    return phrases


def side_phrases(rows: list[dict]) -> dict:
    """{'left': [...], 'right': [...]}: up to SHOWN phrases each side alone used, most outlets first, each with the
    outlets that used it; {} when either side has fewer than MIN_SIDE rated outlets on the story. `rows` are the
    story's headlines, one per outlet (title, agency, bias, rated)."""
    outlets = {'left': set(), 'right': set()}
    used = defaultdict(lambda: {'left': set(), 'right': set()})
    for row in rows:
        s = side(row)
        if s is None:
            continue
        outlets[s].add(row['agency'])
        for phrase in bigrams(row['title']):
            used[phrase][s].add(row['agency'])
    if min(len(outlets['left']), len(outlets['right'])) < MIN_SIDE:
        return {}
    out = {'left': [], 'right': []}
    for phrase, by in used.items():
        for s, other in (('left', 'right'), ('right', 'left')):
            n = len(by[s])
            if n >= MIN_OUTLETS and n >= MIN_SHARE * len(outlets[s]) and not by[other]:
                out[s].append({'phrase': phrase, 'outlets': sorted(by[s]), 'count': n})
    for s in out:
        out[s] = joined(out[s])
        out[s].sort(key=lambda p: (-p['count'], p['phrase']))  # most outlets first
        out[s] = out[s][:SHOWN]
    return out if out['left'] or out['right'] else {}
