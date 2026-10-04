"""The Supreme Court page (#144): this term's cases and who's covering them, from which side and at which stage, from
the last two weeks of headlines (app.analysis.scotus)."""
from datetime import datetime as dt

from app.analysis import scotus
from app.site.common import TemplateHandler, chip_style
from app.site.page_edits import eastern
from app.utils import Config, get_logger

logger = get_logger(__name__)
SHOWN = 8  # headlines shown per case before "more"


def court_date(text):
    """'10/5/26' -> a date, for sorting and 'Oct 5'."""
    return dt.strptime(text, '%m/%d/%y').date() if text else None


class CourtPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('court.html')
        self.context = {'title': 'Supreme Court'}

    def generate(self):
        logger.info("Generating Supreme Court page...")
        if not Config.debug:
            scotus.refresh_docket()  # at most one request a week
        data = scotus.coverage()

        def rows(headlines):
            return [{**h, 'style': chip_style(h['agency'], h['bias']), 'when': eastern(h['first']),
                     'emoji': scotus.STAGE_EMOJI.get(h['stage'], '⚖️')} for h in headlines]

        def dates(case):
            argued = court_date(case.get('argued'))
            return {'argued_on': argued, 'argued_text': f"{argued:%b} {argued.day}" if argued else None,
                    'docket_url': f"https://www.supremecourt.gov/docket/docketfiles/html/public/{case['docket']}.html"}
        covered = [{**c, **dates(c), 'rows': rows(c['headlines'])} for c in data['covered']]
        term_cases = sorted(({**c, **dates(c)} for c in data['cases']),
                            key=lambda c: (c['argued_on'] is None, c['argued_on'] or dt.max.date(), c['name']))
        today = dt.now().date()
        self.context.update({
            'term': data['term'], 'source': data['source'], 'window_days': data['window_days'], 'total': data['total'],
            'covered': covered, 'term_cases': term_cases, 'today': today, 'shown': SHOWN,
            'other': {**data['other'], 'rows': rows(data['other']['headlines'])},
            'stage_emoji': scotus.STAGE_EMOJI,
        })
        self.template.write(self.context)
        logger.info("...%d cases in the news, %d other Court headlines", len(covered), len(data['other']['headlines']))
