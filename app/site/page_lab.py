"""The Lab (Oct 27, the person: "should we also expose some experiments on the site?"): every experiment we've run on
the pipeline, by its folklore codename, its question, where it stands and what it found, from the experiment catalog
(scripts/experiments/catalog.py keeps them in experiments.sqlite). The method is open (the licensing plan of Oct 12:
code AGPL, method CC BY); the papers stay in the data folder, since they quote the private casebook. Each experiment's
hypothesis was written before it ran: that's the point of showing the misses too."""
import os
import sqlite3

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
STATUS = {'in production': ('🏭', 'in use on the site'), 'answered': ('✅', 'answered'),
          'not kept': ('🗑️', 'tried, not kept'), 'unproven': ('🤷', 'unproven either way'),
          'running': ('⏳', 'running'), 'your call': ('🙋', 'waiting on a decision'), 'planned': ('📝', 'planned'),
          'not yet': ('📝', 'not run yet'), 'not run': ('🔁', 'being run again')}
ORDER = ['in production', 'answered', 'running', 'not run', 'your call', 'unproven', 'not kept', 'not yet', 'planned']


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
    return sorted(out, key=lambda x: (ORDER.index(x['status']) if x['status'] in ORDER else 99, x['code']))


class LabPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('lab.html')

    def generate(self):
        logger.info("Generating lab page...")
        found = experiments()
        families = [{'key': f, 'about': about, 'items': [x for x in found if x['family'] == f]}
                    for f, about in FAMILIES.items()]
        counts = {}
        for x in found:
            counts[x['status']] = counts.get(x['status'], 0) + 1
        self.template.write({'title': 'The Lab', 'families': [f for f in families if f['items']], 'total': len(found),
                             'counts': [(STATUS.get(s, ('🧪', s))[0], STATUS.get(s, ('🧪', s))[1], n)
                                        for s, n in sorted(counts.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99)],
                             'og_description': f"{len(found)} experiments on how bignews.day reads the stories people "
                                               "tell, each named after a figure from folklore, with what each found."})
        logger.info("...%d experiments", len(found))
