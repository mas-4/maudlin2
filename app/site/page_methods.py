"""The methods log on the site: docs/methods-log.md as a page, so every change to how bignews.day collects or
measures things (and every mistake and its fix) is public and dated, for anyone reading the numbers or using the
data. Rendered from the same file the repository keeps, so the two never differ.

Oct 28 (the site redo): it was about 25 days of dense paragraphs straight on the patterned background, opening with a
wall of date links. Now it's a timeline: each entry one line (its bold lead), colored by the part of the site it
touches and tagged by kind, with its full text folded under the line; a key filters by area. Both are read from the
lead by the simple rules below (keywords, the first one named wins), never written into the log, so the file stays
as it is; when the rules can't tell, an entry is 🔧 changed, and its area is "the site and its running"."""
import os
import re
from html import escape

import mistune

from app.site.common import TemplateHandler
from app.utils import Constants, get_logger

logger = get_logger(__name__)

LOG = os.path.join(Constants.Paths.ROOT, 'docs', 'methods-log.md')

# The parts of the site an entry can touch, in the key's order: key, emoji, name, color (fixed to the area, never
# cycled, none the lean blue or red) and the words in a lead that name it. The area is the one whose word comes
# first in the lead ("Show claims tied to stories" is about shows); a lead naming none is read from its next sentence.
AREAS = [
    ('front', '📰', 'front pages', '#ffc400',
     r"front[- ]pages?|headlines?|bylines?|photo credits?|word cloud|cloud paper|news[- ]day|scrap\w*|live (?:pages?|blogs?)|"
     r"spelling|quotes?|quote selection|wording|daily editions?|top stories|the nav|rss feed|play page|headline games"),
    ('stories', '🗞️', 'stories and sagas', '#ff4fa3',
     r"stor(?:y|ies)|sagas?|momentum|crossing watch|who stayed|blindspots?|trending|who's in the news|names merged|"
     r"supreme court|snapshots"),
    ('outlets', '🏢', 'outlets', '#00c2a8',
     r"outlets?|sinclair|national desk|breitbart|bloomberg|reuters|washington post|washington times|aggregators?|"
     r"wire share|lean estimate|ratings?|new outlets"),
    ('shows', '🎙️', 'shows, TV and radio', '#ff6b1a',
     r"shows?|show's|podcasts?|episodes?|transcri\w*|whisper|on tv|tv and radio|radio|call-in|jubilee|briefings?|"
     r"presenters?|satire|the replay|focus group"),
    ('motifs', '🧩', 'motifs and folklore', '#8a5cff',
     r"motifs?|motifs'|folklore|rumou?rs?|narratives?|claims?|tellings?|filings?|filed|shortlist\w*|reranker|"
     r"judge|checker\w*|check list|proposer|proposals|seeds?|genres?|rests on|kind of|villain|scope-note|"
     r"fact-checks?|bluesky|posts|the aisle|almanac|carrying words|hold|thompson\w*|conspiracy|confidence model|"
     r"dispute|arguing|watch lists|divide|sides counted|told|answered|came up on|decisions|weak fits|accused"),
    ('measures', '📏', 'measures and models', '#7bc96f',
     r"models?|embedd\w*|mood|emotions?|feelings?|scores?|rubric|thresholds?|gemma|nimble|cpu|provenance|"
     r"hand labels|spiciness|spin|labels?|measures?|bigger embedding|duplicates"),
    ('site', '🛠️', 'the site and its running', '#ffffff',
     r"hourly run|backups?|visits|goatcounter|licensing|dashboard|archive begins|gap|built by hand|rebuilt"),
]
OTHER = AREAS[-1][:4]  # and where no area's word is found
AREA_WORDS = [(k, re.compile(r'\b(?:' + words + r')\b', re.I)) for k, _, _, _, words in AREAS]

# What kind of change, from the lead: checked in this order, the first that fits wins; none fits, 🔧 changed
KINDS = [
    ('fix', '🐛', 'a mistake caught',
     re.compile(r"\bno longer\b|\bfix|\bbugs?\b|mistakes?|\bwrong\b|\berrors?\b|misread|mishear|withheld|\bleak|"
                r"honest now|were being|had moved|^gap\b|loops\b|failure|privacy|junk|scrubbed|retry", re.I)),
    ('dropped', '🗑️', 'tried, not kept',
     re.compile(r"\btried\b|not adopted|not kept|dropped|came down|removed|retired|held back|\bno more\b|"
                r"out of the public", re.I)),
    ('new', '🆕', 'new',
     re.compile(r"\bnew\b|\bbegins?\b|\(#\d+|\bcan be\b|archived|^more\b|\btwo more\b|\badded\b|embedded|exported|^on tv\b|"
                r"^on the radio|^a dashboard|^the replay\.?$|^the election almanac\.?$", re.I)),
]
CHANGED = ('changed', '🔧', 'changed')

_ITEM = re.compile(r'^- (.*)$')
_LEAD = re.compile(r'^\*\*(.+?)\*\*\s*', re.S)


def area_of(lead: str, rest: str = '') -> str:
    """The area an entry touches: the one whose word comes first in its lead, else in the sentence after it"""
    for text in (lead, re.split(r'(?<=[.;:])\s', rest.strip(), maxsplit=1)[0] if rest else ''):
        hits = [(m.start(), i, k) for i, (k, rx) in enumerate(AREA_WORDS) if (m := rx.search(text))]
        if hits:
            return min(hits)[2]
    return OTHER[0]


def kind_of(lead: str) -> str:
    return next((k for k, _, _, rx in KINDS if rx.search(lead)), CHANGED[0])


def _day_label(head: str) -> tuple[str, str, str]:
    """A section's heading as (anchor, label, short): '2026-10-03 (evening)' -> ('2026-10-03-evening',
    'Oct 3, evening', '3🌙'); one that isn't a date (History) -> ('history', 'History', '🕰️')"""
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})\s*(?:\((.+)\))?', head)
    if not m:
        return re.sub(r'\W+', '-', head.lower()).strip('-'), head, '🕰️'
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    y, mo, d, note = m.groups()
    anchor = f'{y}-{mo}-{d}' + (f"-{re.sub(r'\W+', '-', note.lower())}" if note else '')
    return (anchor, f'{months[int(mo) - 1]} {int(d)}' + (f', {note}' if note else ''),
            str(int(d)) + ('🌙' if note else ''))


def inline(text: str) -> str:
    """A lead as one line of html: escaped, its `code` and *italics* kept"""
    html = mistune.html(escape(text, quote=False)).strip()
    return html[3:-4] if html.startswith('<p>') and html.endswith('</p>') else html


def entries(block: list[str]) -> list[str]:
    """A section's lines as its top-level list items, each item's markdown with its continuation lines dedented"""
    items = []
    for line in block:
        if _ITEM.match(line):
            items.append([_ITEM.match(line).group(1)])
        elif items:
            items[-1].append(line[2:] if line.startswith('  ') else line)
    return ['\n'.join(i).strip() for i in items]


def parse(text: str) -> list[dict]:
    """The log as days, newest first as the file has them: [{anchor, label, short, entries: [{line, body (html), area,
    kind}]}]; the file's own title and opening paragraph are the page's, so they're left out"""
    days = []
    for section in re.split(r'^## ', text, flags=re.M)[1:]:
        head, _, rest = section.partition('\n')
        anchor, label, short = _day_label(head.strip())
        out = []
        for item in entries(rest.splitlines()):
            m = _LEAD.match(item)
            lead = m.group(1).strip() if m else item.split('\n')[0]
            more = item[m.end():] if m else item[len(lead):]
            line = lead.rstrip(' .;:')
            out.append({'line': line, 'line_html': inline(line),
                        'body': mistune.html(more.strip()) if more.strip() else '',
                        'area': area_of(lead, more), 'kind': kind_of(line)})
        if out:
            days.append({'anchor': anchor, 'label': label, 'short': short, 'entries': out})
    return days


def keys(days: list[dict]) -> tuple[list[dict], list[dict]]:
    """The areas' and the kinds' keys, each with how many entries it has"""
    count = lambda field, k: sum(e[field] == k for d in days for e in d['entries'])  # noqa: E731
    areas = [{'key': k, 'mark': e, 'name': n, 'ink': ink, 'count': count('area', k)}
             for k, e, n, ink, _ in AREAS]
    kinds = [{'key': k, 'mark': e, 'name': n, 'count': count('kind', k)}
             for k, e, n in [k[:3] for k in KINDS] + [CHANGED]]
    return [a for a in areas if a['count']], kinds


class MethodsPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('methods.html')

    def generate(self):
        logger.info("Generating methods page...")
        with open(LOG) as f:
            days = parse(f.read())
        areas, kinds = keys(days)
        look = {a['key']: a for a in areas}
        kind_look = {k['key']: k for k in kinds}
        for d in days:
            for e in d['entries']:
                e['area_mark'], e['area_name'], e['ink'] = look[e['area']]['mark'], look[e['area']]['name'], look[e['area']]['ink']
                e['kind_mark'], e['kind_name'] = kind_look[e['kind']]['mark'], kind_look[e['kind']]['name']
        top = max((len(d['entries']) for d in days), default=1)
        self.template.write({'title': 'Methods log', 'days': days, 'areas': areas, 'kinds': kinds, 'top': top,
                             'total': sum(len(d['entries']) for d in days)})
        logger.info("...%d dated sections", len(days))
