"""How many separate occasions a motif is told on: the praxis's repetition bar, checked on the motif rather than on
the claim (Fable's reading of the index, Oct 12). A claim from posts already has many tellers and a show claim two
shows, so nearly every claim is retold; the question for a motif is whether its shape turns up on more than one
occasion, or is one event told many ways (eleven claims about one Cornell case are one occasion).

A motif's kept claims are joined into one occasion when two of them

    read alike             mxbai likeness at least ALIKE (versions of one telling)
    come from one source   the same fact-check, show claim or focus-group episode (a posts claim's ref is only the
                           report's time, so not those)
    share a rare name      a name (capitalized words) found in at most RARE of all the index's claims, not a word also
                           used in lower case nor a people's name ('Cornell University' joins; 'Republican' doesn't)
    share a story          the same news story on both filings (motif_index's story ids, Oct 12: the person's tier
                           two), merged stories followed; a posts claim tied to a story only as 'same issue' doesn't

and the occasions are what's left apart. An estimate: a name can join two affairs of one person, and a story told
with no names in common splits in two. Kept on each entry as 'told', refreshed in the hourly run after filing:

    {'events': 3, 'sources': ['narrative', 'shows'], 'span': ['2026-09-30', '2026-10-11'], 'at': <run time>}

A motif is attested when told on two occasions or more, placed otherwise (motif_index.attested)."""
import re
from collections import Counter
from datetime import datetime as dt

import numpy as np

from app.analysis import motif_index as mi
from app.utils import get_logger

logger = get_logger(__name__)

ALIKE = 0.72  # below the narratives' 0.78: a claim retold with a new development still reads as the same occasion
RARE = 25  # a name in more of the index's claims than this (Trump, Iran) says nothing about which event
NAME = re.compile(r"\b[A-Z][\w'’-]*(?:\s+(?:of\s+)?[A-Z][\w'’-]*)*")
WORD = re.compile(r"\b[a-z][\w-]*")


def names(text: str) -> set[str]:
    """Capitalized runs in a claim ('Cornell University', 'Ken Paxton'), less a lone first word of the sentence"""
    out = set()
    for m in NAME.finditer(text):
        w = re.sub(r"['’]s$", '', m.group(0))
        if len(w) >= 3 and not (m.start() == 0 and ' ' not in w):
            out.add(w)
    return out


def telling_names(claims: list[str]) -> dict[str, set[str]]:
    """Each claim's names that can tell one occasion from another: rare in the whole index, and not a common word"""
    of = {c: names(c) for c in claims}
    df = Counter(n for s in of.values() for n in s)
    lower = {w for c in claims for w in WORD.findall(c)}
    generic = {n for n in df if ' ' not in n and (n.lower() in lower or n.endswith(('an', 'ans')))}  # Fire, Iranian
    return {c: {n for n in s if df[n] <= RARE and n not in generic} for c, s in of.items()}


def story(c: dict, merged: dict) -> int | None:
    """The news story a filing is about, as an event (not a 'same issue' tie), merges followed"""
    if c.get('story') is None or c.get('story_tie') == 'same issue':
        return None
    try:
        sid = int(c['story'])
    except (TypeError, ValueError):
        return None
    return merged.get(sid, sid)


def occasions(claims: list[dict], vec: dict, named: dict, merged: dict | None = None) -> list[list[dict]]:
    """A motif's claims in occasions (see the module's note)"""
    merged = merged or {}
    stories = [story(c, merged) for c in claims]
    n = len(claims)
    root = list(range(n))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    v = np.array([vec[c['claim']] for c in claims]) if n else np.zeros((0, 1))
    alike = v @ v.T
    for i in range(n):
        for j in range(i + 1, n):
            a, b = claims[i], claims[j]
            same = a.get('source') != 'narrative' and a.get('ref') and a.get('ref') == b.get('ref')
            if (alike[i, j] >= ALIKE or same or named[a['claim']] & named[b['claim']]
                    or (stories[i] is not None and stories[i] == stories[j])):
                root[find(i)] = find(j)
    out = {}
    for i in range(n):
        out.setdefault(find(i), []).append(claims[i])
    return list(out.values())


def told(index: dict) -> dict[str, dict]:
    """Every live motif's 'told', from its kept claims (checked ✓, or filed by hand)"""
    from app.narratives import embed
    kept = {e['id']: [c for c in e['claims'] if c.get('checked') == 'yes'] for e in mi.live(index)}
    texts = sorted({c['claim'] for cs in kept.values() for c in cs})
    vec = dict(zip(texts, embed(texts))) if texts else {}
    named = telling_names(texts)
    try:
        from app.analysis import stories
        merged = stories.merges()
    except Exception:  # noqa: BLE001 - without the merges, story ids as they are
        merged = {}
    at = dt.now().isoformat(timespec='seconds')
    out = {}
    for eid, cs in kept.items():
        dates = sorted(c['date'] for c in cs if c.get('date'))
        out[eid] = {'events': len(occasions(cs, vec, named, merged)), 'sources': sorted({c.get('source', '') for c in cs}),
                    'span': [dates[0], dates[-1]] if dates else [], 'at': at}
    return out


def refresh() -> int:
    """The hourly run's part: work out every motif's occasions and keep them on the entries"""
    counts = told(mi.load())
    mi.set_told(counts)
    attested = sum(1 for t in counts.values() if t['events'] >= 2)
    logger.info("Motif occasions: %d of %d motifs told on two or more", attested, len(counts))
    return attested
