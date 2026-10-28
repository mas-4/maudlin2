"""The Lab (Oct 27, the person: "should we also expose some experiments on the site?"): every experiment we've run on
the pipeline, by its folklore codename, its question, where it stands and what it found, from the experiment catalog
(scripts/experiments/catalog.py keeps them in experiments.sqlite). The method is open (the licensing plan of Oct 12:
code AGPL, method CC BY); the papers stay in the data folder, since they quote the private casebook. Each experiment's
hypothesis was written before it ran: that's the point of showing the misses too.

Oct 28 (the site redo): 76 identical cards became a ladder per family, from what's in use at the top down to what was
tried and not kept, each rung colored by where it stands (the status chips at the top are the key and filter by it),
with a before → after bar where the result gives a measure going from one number to another, and the question and the
full result in the row's hover card. Results are free text, so only the plain "A to B" shape is read (see
before_after); everything else gets no bar rather than a guessed one."""
import os
import re
import sqlite3

from app.site import boards
from app.site.common import TemplateHandler
from app.utils import get_logger
from app.utils.config import Config

logger = get_logger(__name__)

DB = os.path.join(Config.data, 'motifs', 'experiments', 'experiments.sqlite')
FAMILIES = {'E': "the shortlist: finding a claim's motifs", 'J': 'the judge: does this claim fit this motif?',
            'F': 'filing: fewer corrections for the person', 'A': 'archives: our method on outside material',
            'S': 'stories and sagas', 'U': 'the machine alone, without a person', 'P': 'proposing and naming motifs',
            'D': 'ideas from the research', 'R': 'the reranker', 'C': 'a cascade of models', 'M': 'one model for another',
            'W': 'wording claims', 'G': 'genre and group descriptions', 'ASR': 'transcribing the shows'}
# Each family's banner: an emoji and a short name (the banner shouts in Bungee, so a few words); FAMILIES says the rest
FAMILY_TITLE = {'E': ('🎯', 'The shortlist'), 'J': ('🧑‍⚖️', 'The judge'), 'F': ('🗂️', 'Filing'),
                'A': ('📚', 'The archives'), 'S': ('🗞️', 'Stories and sagas'), 'U': ('🤖', 'The machine alone'),
                'P': ('💡', 'Proposals'), 'D': ('📖', 'From the research'), 'R': ('🥇', 'The reranker'),
                'C': ('🪜', 'A cascade'), 'M': ('🔁', 'One model for another'), 'W': ('✍️', 'Wording claims'),
                'G': ('🏷️', 'Genres and groups'), 'ASR': ('🎧', 'Transcribing the shows')}
STATUS = {'in production': ('🏭', 'in use on the site'), 'answered': ('✅', 'answered'),
          'not kept': ('🗑️', 'tried, not kept'), 'unproven': ('🤷', 'unproven either way'),
          'running': ('⏳', 'running'), 'your call': ('🙋', 'waiting on a decision'), 'planned': ('📝', 'planned'),
          'not yet': ('📝', 'not run yet'), 'not run': ('🔁', 'being run again')}
ORDER = ['in production', 'answered', 'running', 'not run', 'your call', 'unproven', 'not kept', 'not yet', 'planned']
# Where it stands, as a color: fixed to the status, in ORDER, never cycled; none is the lean blue or red. Running and
# being run again share orange (both under way; their emoji tell them apart); what hasn't run stays white.
STATUS_INK = {'in production': '#00c2a8', 'answered': '#8a5cff', 'running': '#ff6b1a', 'not run': '#ff6b1a',
              'your call': '#ffc400', 'unproven': '#c9c9d6', 'not kept': '#6b6f78', 'not yet': '#ffffff',
              'planned': '#ffffff'}
BANNER = '#ff4fa3'  # every family's banner, one color: the rows carry the status colors

# "A to B" in a result: two plain numbers, both percentages or both between 0 and 1 (an AUC, a precision), neither
# signed (a "+1.7 to +4.2" is an interval of a gain, not a before and after) nor part of a range ("53% to 64-67%")
_NUM = r'(\d+(?:\.\d+)?)'
BEFORE_AFTER = re.compile(r'(?<![\d.+\-−])' + _NUM + r'(%?) to ' + _NUM + r'(%?)(?![\d.\-–])')


def before_after(result: str) -> dict | None:
    """The first "A to B" in a result as {before, after, scale, figure}, or None when it has none we can read safely:
    both sides must be percentages (on 0-100) or both plain numbers no bigger than 1 (on 0-1); counts, words and dates
    in the same shape are left alone, as their scale isn't known"""
    for m in BEFORE_AFTER.finditer(result or ''):
        a, pa, b, pb = m.groups()
        a, b = float(a), float(b)
        if pa and pb and a <= 100 and b <= 100:
            return {'before': a, 'after': b, 'scale': 100, 'figure': f'{m.group(1)}% → {m.group(3)}%'}
        if not pa and not pb and a <= 1 and b <= 1:
            return {'before': a, 'after': b, 'scale': 1, 'figure': f'{m.group(1)} → {m.group(3)}'}
    return None


def _code_key(code: str) -> tuple:
    """E0.1, E1, E2 … E11, F1 … F28: by letters, then each number in turn (as text and number, so they compare)"""
    return tuple((0, int(p), '') if p.isdigit() else (1, 0, p) for p in re.findall(r'\d+|\D+', code))


def experiments() -> list[dict]:
    """Every experiment in the catalog: code, codename, family, question, status, its emoji and words, result"""
    if not os.path.exists(DB):
        return []
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    rows = con.execute('select code, codename, family, name, status, result, updated from experiments').fetchall()
    out = []
    for code, codename, family, name, status, result, updated in rows:
        emoji, words = STATUS.get(status, ('🧪', status or ''))
        fam = family if family in FAMILIES else next((f for f in sorted(FAMILIES, key=len, reverse=True)
                                                       if code.startswith(f)), '')
        out.append({'code': code, 'codename': codename or code, 'family': fam, 'question': name or '',
                    'status': status or '', 'emoji': emoji, 'words': words, 'result': result or '',
                    'updated': (updated or '')[:10]})
    return sorted(out, key=lambda x: (ORDER.index(x['status']) if x['status'] in ORDER else 99, _code_key(x['code'])))


def rung(x: dict) -> dict:
    """One experiment as a row of its family's ladder: its status as the disc, its codename, a before → after bar
    where the result has one, and the question and result for the hover card"""
    ba = before_after(x['result'])
    tip = '\n'.join(filter(None, [f"❓ {x['question']}", f"🔬 {x['result']}" if x['result'] else '',
                                  f"{x['emoji']} {x['words']}" + (f", updated {x['updated']}" if x['updated'] else '')]))
    r = boards.row(x['codename'], None, 0, 0, ba['figure'] if ba else '', tip=tip,
                   ink=STATUS_INK.get(x['status'], boards.UNCOLORED), mark=x['emoji'], mark_label=x['words'])
    r.update({'code': x['code'], 'status': x['status'], 'head': f"{x['codename']} · {x['code']}",
              'before': round(100 * ba['before'] / ba['scale'], 1) if ba else None,
              'after': round(100 * ba['after'] / ba['scale'], 1) if ba else None})
    return r


def ladders(found: list[dict]) -> list[dict]:
    """A board per family, in FAMILIES order, its rows the family's experiments from in use down to not kept"""
    out = []
    for f, about in FAMILIES.items():
        items = [x for x in found if x['family'] == f]
        if items:
            emoji, title = FAMILY_TITLE.get(f, ('🧪', f))
            out.append(boards.board(f.lower(), emoji, title, BANNER, f'{f} · {about}', [rung(x) for x in items]))
    return out


def status_key(found: list[dict]) -> list[dict]:
    """The status colors, in ORDER, with how many experiments each has: the key, and the filter"""
    counts = {}
    for x in found:
        counts[x['status']] = counts.get(x['status'], 0) + 1
    return [{'status': s, 'mark': STATUS.get(s, ('🧪', s))[0], 'name': STATUS.get(s, ('🧪', s))[1],
             'ink': STATUS_INK.get(s, boards.UNCOLORED), 'count': n}
            for s, n in sorted(counts.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99)]


class LabPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('lab.html')

    def generate(self):
        logger.info("Generating lab page...")
        found = experiments()
        self.template.write({'title': 'The Lab', 'ladders': ladders(found), 'total': len(found),
                             'key': status_key(found), 'with_bar': sum(1 for x in found if before_after(x['result'])),
                             'og_description': f"{len(found)} experiments on how bignews.day reads the stories people "
                                               "tell, each named after a figure from folklore, with what each found."})
        logger.info("...%d experiments", len(found))
