"""Quote selection (#149): which phrase each outlet puts in quotation marks on a story. On the $90 Medicare checks,
some outlets quoted "slush fund" and others "wonderful seniors"; the phrase an outlet chooses to quote is a framing
choice in plain sight, with no model involved."""
import re
from collections import Counter, defaultdict

# A quoted phrase: opening quote at the start or after a space or bracket, closing quote before a space, punctuation
# or the end, so the apostrophe in "Trump's" doesn't open a quote
QUOTE = re.compile(r"(?:(?<=[\s(\[—–-])|^)[‘“\"']([^‘’“”\"\n]{2,80}?)[’”\"'](?=[\s,.:;?!)\]—–-]|$)")
MAX_ON_CARD = 4


def quoted(title: str) -> list[str]:
    return [m.group(1).strip() for m in QUOTE.finditer(title) if m.group(1).strip()]


def key(phrase: str) -> str:
    return re.sub(r'[^\w\s]', '', phrase.lower()).strip()


def side(row: dict) -> str:
    if not row.get('rated'):
        return 'unrated'
    return 'left' if row['bias'] < 0 else 'right' if row['bias'] > 0 else 'center'


def nested(phrases: list[str]) -> list[list[str]]:
    """Group quote keys where one sits inside another, whole words ('bad things' in 'world should accept some bad
    things'): one quote cut differently by different outlets, which as separate chips stacked a card with the same
    words."""
    parent = {k: k for k in phrases}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k
    for a in phrases:
        for b in phrases:
            if a != b and f' {a} ' in f' {b} ':
                parent[root(a)] = root(b)
    groups = defaultdict(list)
    for k in phrases:
        groups[root(k)].append(k)
    return list(groups.values())


def story_quotes(rows: list[dict]) -> list[dict]:
    """The phrases a story's outlets quoted (one headline per outlet), most-quoted first: how each is spelled most
    often, which outlets quoted it, and from which side. Quotes inside one another count as one, shown as the wording
    most outlets used (the longer on a tie: 'concerted' alone says less than
    'concerted effort to intimidate the court'), the others kept as variants."""
    found = defaultdict(lambda: {'spellings': Counter(), 'outlets': {}})
    for row in rows:
        for phrase in quoted(row['title']):
            k = key(phrase)
            if not k:
                continue
            found[k]['spellings'][phrase] += 1
            found[k]['outlets'][row['agency']] = side(row)
    out = []
    for group in nested(list(found)):
        group.sort(key=lambda k: (-len(found[k]['outlets']), -len(k)))
        outlets = {}
        for k in group:
            outlets.update(found[k]['outlets'])
        spell = [found[k]['spellings'].most_common(1)[0][0] for k in group]
        sides = Counter(outlets.values())
        rated = {s: sides.get(s, 0) for s in ('left', 'center', 'right')}
        lead = max(rated, key=rated.get) if any(rated.values()) else 'unrated'
        if list(rated.values()).count(rated.get(lead, 0)) > 1 and rated.get(lead):
            lead = 'mixed'  # a tie between sides
        out.append({'phrase': spell[0], 'variants': spell[1:], 'outlets': sorted(outlets), 'count': len(outlets),
                    **rated, 'unrated': sides.get('unrated', 0), 'lead': lead})
    out.sort(key=lambda q: (-q['count'], q['phrase'].lower()))
    return out[:MAX_ON_CARD]
