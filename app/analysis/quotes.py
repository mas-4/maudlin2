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


def story_quotes(rows: list[dict]) -> list[dict]:
    """The phrases a story's outlets quoted (one headline per outlet), most-quoted first: how each is spelled most
    often, which outlets quoted it, and from which side."""
    found = defaultdict(lambda: {'spellings': Counter(), 'outlets': {}})
    for row in rows:
        for phrase in quoted(row['title']):
            k = key(phrase)
            if not k:
                continue
            found[k]['spellings'][phrase] += 1
            found[k]['outlets'][row['agency']] = side(row)
    out = []
    for entry in found.values():
        sides = Counter(entry['outlets'].values())
        rated = {s: sides.get(s, 0) for s in ('left', 'center', 'right')}
        lead = max(rated, key=rated.get) if any(rated.values()) else 'unrated'
        if list(rated.values()).count(rated.get(lead, 0)) > 1 and rated.get(lead):
            lead = 'mixed'  # a tie between sides
        out.append({'phrase': entry['spellings'].most_common(1)[0][0], 'outlets': sorted(entry['outlets']),
                    'count': len(entry['outlets']), **rated, 'unrated': sides.get('unrated', 0), 'lead': lead})
    out.sort(key=lambda q: (-q['count'], q['phrase'].lower()))
    return out[:MAX_ON_CARD]
