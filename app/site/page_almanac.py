"""The Election Almanac page (Oct 28): which election story shapes we forecast to surge in election week, Nov 3-9,
frozen before the polls open and scored afterwards, win or lose (app/analysis/almanac.py). Before the window nothing
is scored; during it the numbers so far are marked provisional; from the count day, Nov 17, they are final."""
from datetime import date, datetime

from markupsafe import Markup

from app.analysis import almanac
from app.site.common import TemplateHandler, j2env, motif_href
from app.utils import get_logger

logger = get_logger(__name__)

CATEGORIES = [('integrity', '🗳️', 'Is the vote honest?'), ('count and result', '🧮', 'The count and the result'),
              ('polls and forecasts', '📊', 'Polls and forecasts'), ('midterm dynamics', '🌊', 'Midterm dynamics'),
              ('election-day talk', '🙋', 'Election-day talk')]
CATEGORY_POP = {'integrity': '#8a5cff', 'count and result': '#ff6b1a', 'polls and forecasts': '#3a86ff',
                'midterm dynamics': '#00c2a8', 'election-day talk': '#ff4fa3'}
BAR_W, BAR_H = 300, 26


def bar(p: float, base: float, pop: str) -> Markup:
    """p_surge as a bar on 0-100%, with the reference forecaster's base rate as a dashed line"""
    w, bx = round(BAR_W * p, 1), round(BAR_W * base, 1)
    return Markup(
        f'<svg class="almanac-bar" viewBox="0 0 {BAR_W + 4} {BAR_H + 4}" role="img" '
        f'aria-label="{p:.0%} chance of a surge; the yardstick is {base:.0%}">'
        f'<title>{p:.0%} chance of a surge (the yardstick gives every motif {base:.0%})</title>'
        f'<rect x="2" y="2" width="{BAR_W}" height="{BAR_H}" rx="6" fill="#fff" stroke="#1f1f2e" stroke-width="2"/>'
        f'<rect x="2" y="2" width="{w}" height="{BAR_H}" rx="6" fill="{pop}" stroke="#1f1f2e" stroke-width="2"/>'
        f'<line x1="{bx + 2}" y1="0" x2="{bx + 2}" y2="{BAR_H + 4}" stroke="#1f1f2e" stroke-width="2.5" '
        f'stroke-dasharray="4 3"/></svg>')


def eastern_time(stamp: str) -> str:
    t = datetime.fromisoformat(stamp).astimezone(almanac.EASTERN)
    return t.strftime('%b %-d, %Y, %-I:%M %p ET')


def day(iso: str) -> str:
    return date.fromisoformat(iso).strftime('%b %-d')


def span(first: str, last: str) -> str:
    """Nov 3–9, or Oct 27–Nov 2 across a month"""
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return f"{day(first)}–{b.day if a.month == b.month else day(last)}"


class AlmanacPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('almanac.html')

    def context(self, forecast: dict, rows: list[dict], public: set[str], pages: set[str] | None,
                today: date) -> dict:
        names = {f['id']: f['name'] for f in forecast['forecasts']} | forecast.get('names', {})

        def link(m: str) -> dict:
            """A motif by name, linked to its page when it has one (motifs not public yet have none)"""
            has_page = m in pages if pages is not None else m in public
            return {'id': m, 'name': names.get(m, m), 'href': motif_href(m) if has_page else None}

        scored = almanac.score(forecast, rows, public, today)
        st = scored['stage']
        base = forecast['base_rate']
        groups = []
        for cat, emoji, label in CATEGORIES:
            fs = sorted((f for f in forecast['forecasts'] if f['category'] == cat), key=lambda f: -f['p_surge'])
            if fs:
                groups.append({'emoji': emoji, 'label': label, 'pop': CATEGORY_POP[cat],
                               'rows': [{**f, **link(f['id']), 'bar': bar(f['p_surge'], base, CATEGORY_POP[cat]),
                                         'needs': 2 * f['oct_share_pct'], 'out': scored['motifs'].get(f['id'])}
                                        for f in fs]})
        calls = [{**c, 'links': [link(m) for m in c['motifs']], 'out': o}
                 for c, o in zip(forecast['answer_calls'], scored['answers'] or [None] * len(forecast['answer_calls']))]
        brennan = [{**t, 'links': [link(m) for m in t['motifs']]} for t in forecast['brennan']['themes']]
        seal = forecast.get('frozen') or {}
        ps = [f['p_surge'] for f in forecast['forecasts']]
        top = sorted(forecast['forecasts'], key=lambda f: -f['p_surge'])[:3]
        try:
            from app.site import share_images
            image = share_images.almanac_card([(f['name'], f['p_surge']) for f in top], st, scored.get('skill'))
        except Exception as err:  # noqa: BLE001 - the page stands without its card
            logger.warning("Almanac: share card: %s", err)
            image = None
        dates = forecast['dates']
        return {
            'title': 'The Election Almanac', 'og_title': '🔮 The Election Almanac · bignews.day',
            'og_description': 'Which election stories will surge in election week? A forecast published before the '
                              'polls open and scored afterwards, win or lose.',
            'og_image': image, 'og_image_alt': 'The Election Almanac: the story shapes we forecast to surge, '
                                               + ', '.join(f"{f['name']} {f['p_surge']:.0%}" for f in top),
            'stage': st, 'seal': seal, 'frozen_at': eastern_time(seal['at']) if seal.get('at') else '',
            'scored': scored, 'groups': groups, 'calls': calls, 'brennan': brennan,
            'brennan_meta': forecast['brennan'], 'rules': forecast['rules'], 'base': base,
            'conditional': [f for f in forecast['forecasts'] if isinstance(f.get('lead_sides'), dict)],
            'n_forecasts': len(ps),'mean_p': sum(ps) / len(ps), 'house': (forecast.get('results') or {}).get('house'),
            'window': span(*dates['window']),'count_day': day(dates['count']),
            'through': day(scored['through']) if scored.get('through') else '',
        }

    def generate(self, today: date | None = None):
        logger.info("Generating the election almanac...")
        forecast = almanac.load()
        try:
            from app.site.page_motif import page_ids, shared
            web = shared()['web']
            rows, public = web['rows'], set(web['entries'])
            pages = j2env.globals.get('motif_pages')
            pages = set(pages) if pages is not None else page_ids()
        except Exception as e:  # noqa: BLE001 - the forecast stands without the tellings; nothing is scored
            logger.warning("Almanac: tellings: %s", e)
            rows, public, pages = [], set(), set()
        ctx = self.context(forecast, rows, public, pages, today or almanac.today_eastern())
        self.template.write(ctx)
        logger.info("...almanac %s, %d forecasts", ctx['stage'], ctx['n_forecasts'])
