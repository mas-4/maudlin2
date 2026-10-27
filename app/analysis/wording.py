"""Each side's wording on a story: the two-word phrases that outlets on one side of the lean scale put in their headlines
and no outlet on the other side does. On the FlyDubai cockpit attack, left-leaning outlets wrote "extremism concerns"
and "terrorist act" while right-leaning ones wrote "hero pilot" and "FlyDubai hijacker"; on the senator's phone
number, "Trump urges" against "Trump doxes". Word choice in plain sight, with no model involved.

Our outlets lean left as a group, so a phrase only the left uses is less telling than one only the right uses unless
both sides are well represented: a story needs MIN_SIDE rated outlets on each side, and a phrase needs MIN_OUTLETS
outlets and MIN_SHARE of its side's outlets, with none on the other side. A phrase whose every word the other side also
wrote, in some form, is the story's own vocabulary rather than framing ("bakker dead" when the left wrote "Bakker
dies"): it's dropped (Oct 6)."""
import re
from collections import defaultdict

from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

MIN_SIDE = 3
MIN_OUTLETS = 3  # Oct 27 audit: at 2, two outlets' incidental detail ("subway platform") read as framing
MIN_LOADED = 1.5  # the headlines carrying the phrase, on average, on the 0-2 loaded-wording scale
# Oct 27 audit: of 60 chips, about 20% framing ("obama judge", "biden admin"), 67% incidental details ("bus stop"),
# 13% fragments ("b star" from R&B, "9 11"). A framing phrase sits in loaded headlines, is used by several outlets,
# and is more than a name: on the day's stories these three cut 45 chips to the 3 that were framing
MIN_SHARE = 0.25
SHOWN = 3
WORD = re.compile(r"[a-z0-9][a-z0-9'’-]*[a-z0-9]|[a-z0-9]")
# Words that make a phrase say nothing about framing: function words, and the filler of headline grammar
FILLER = set(stopwords.words('english')) | {
    'says', 'say', 'said', 'new', 'us', 'u.s', 'report', 'reports', 'amid', 'could', 'would', 'may', 'video',
    'watch', 'live', 'update', 'updates', 'news', 'latest', 'per', 'via', 'gets', 'get', 'set', 'one', 'two',
    # light verbs, whose phrase is the headline's grammar, not its framing ("judge puts" a hold on it, Oct 27)
    'puts', 'put', 'takes', 'take', 'makes', 'make', 'gives', 'give', 'goes', 'go', 'comes', 'come',
}
# Dotted abbreviations written as one word: "D.C. golf" read as "d", "c", "golf" made a phrase "c golf" for the left
# while the right's "DC golf" made "dc golf", one place in two spellings, each side's alone (Oct 27)


def words(title: str) -> list[str]:
    text = title.lower().replace('’', "'")
    text = re.sub(r'\b(?:[a-z]\.){2,}', lambda m: m.group(0).replace('.', ''), text)  # d.c. -> dc, u.s. -> us
    return WORD.findall(text)

# Forms a stemmer doesn't fold together but headlines swap freely
FOLD = {'dead': 'die', 'death': 'die'}  # never 'kill': killed vs. died is framing
_stem = PorterStemmer().stem


def stem(word: str) -> str:
    s = _stem(word.replace("'s", ''))
    return FOLD.get(s, s)


def bigrams(title: str) -> set[str]:
    w = words(title)
    return {f'{a} {b}' for a, b in zip(w, w[1:]) if a not in FILLER and b not in FILLER}


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


def framing(phrase: str, scores: list[float]) -> bool:
    """Whether a phrase reads as framing: its headlines loaded on average (MIN_LOADED; no scores, no chip), no word a
    fragment (one letter, or digits: "b star", "9 11"), and at least one word in the dictionary, so a name alone
    ("abdul el-sayed") isn't framing"""
    words = phrase.split()
    if not scores or sum(scores) / len(scores) < MIN_LOADED:
        return False
    if any(len(w) < 2 or w.isdigit() for w in words):
        return False
    try:
        from nltk.corpus import wordnet as wn
        return any(wn.synsets(w) for w in words)
    except LookupError:
        return True


def side_phrases(rows: list[dict]) -> dict:
    """{'left': [...], 'right': [...]}: up to SHOWN phrases each side alone used, most outlets first, each with the
    outlets that used it; {} when either side has fewer than MIN_SIDE rated outlets on the story. `rows` are the
    story's headlines, one per outlet (title, agency, bias, rated)."""
    outlets = {'left': set(), 'right': set()}
    used = defaultdict(lambda: {'left': set(), 'right': set()})
    vocab = {'left': set(), 'right': set()}  # word stems each side wrote anywhere in its headlines
    loaded = {}  # outlet -> its headline's loaded-wording score
    for row in rows:
        s = side(row)
        if s is None:
            continue
        outlets[s].add(row['agency'])
        loaded[row['agency']] = row.get('loaded_score', row.get('loaded'))
        vocab[s] |= {stem(word) for word in words(row['title'])}
        for phrase in bigrams(row['title']):
            used[phrase][s].add(row['agency'])
    if min(len(outlets['left']), len(outlets['right'])) < MIN_SIDE:
        return {}
    out = {'left': [], 'right': []}
    for phrase, by in used.items():
        for s, other in (('left', 'right'), ('right', 'left')):
            n = len(by[s])
            if n >= MIN_OUTLETS and n >= MIN_SHARE * len(outlets[s]) and not by[other] \
                    and not all(stem(word) in vocab[other] for word in phrase.split()) \
                    and framing(phrase, [loaded[a] for a in by[s] if loaded.get(a) is not None]):
                out[s].append({'phrase': phrase, 'outlets': sorted(by[s]), 'count': n})
    for s in out:
        out[s] = joined(out[s])
        out[s].sort(key=lambda p: (-p['count'], p['phrase']))  # most outlets first
        out[s] = out[s][:SHOWN]
    return out if out['left'] or out['right'] else {}
