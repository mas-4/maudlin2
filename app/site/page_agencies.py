"""The outlets page: every outlet we follow, lined up by lean, with a card each saying how it covers the news (how
loaded its wording is, how grim its news runs, how it frames shared stories against everyone else, how often it
rewrites headlines, and the feeling its headlines stir most). All from the last WINDOW_DAYS of news headlines."""
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz

from app.analysis.edits import find_edits, edit_rates
from app.analysis.newsfilter import EMOTION_EMOJI, EMOTIONS, emotion_weights
from app.analysis.stories import framing_scores
from app.models import Session, Agency, Article, Headline
from app.ratings import LEAN
from app.site.common import chip_style, copy_assets, j2env, TemplateHandler, PathHandler
from app.site.favicons import slug
from app.site.data import DataHandler, DataTypes, NEWS_ONLY
from app.site.graphing import bias_colors, bias_ink
from app.site.page_headlines import weather
from app.site.wordcloudgen import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Bias, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 30
MIN_HEADLINES = 10  # fewer and the averages say little
FRAMING_EVEN = 0.05  # within this of the other outlets on the same stories counts as in line


def flag(country: Country) -> str:
    """A country's flag emoji, from its two-letter code."""
    code = country.name.rstrip('_').upper()
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code)


def spin(loaded: float) -> tuple[str, str]:
    if loaded < 0.25:
        return '🍞', 'plain'
    if loaded < 0.6:
        return '🌶️', 'loaded'
    return '🌶️🌶️', 'loaded+'


def framing_badge(framing: float) -> tuple[str, str]:
    if framing <= -FRAMING_EVEN:
        return '😈', 'gloomier than others'
    if framing >= FRAMING_EVEN:
        return '😇', 'sunnier than others'
    return '🤝', 'in line with others'


def outlet_profiles(live: pd.Series) -> list[dict]:
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=WINDOW_DAYS)
    with Session() as s:
        rows = s.query(
            Agency.name, Agency._bias, Agency.lean_rated, Agency.lean_url, Agency.reliability,  # noqa prot attr
            Agency.reliability_note, Agency._country,
            Headline.event_score, Headline.loaded_score, Headline.emotion_ranks,
        ).join(Headline.article).join(Article.agency).filter(Headline.first_accessed > since, NEWS_ONLY).all()
    df = pd.DataFrame(rows, columns=['agency', 'bias', 'rated', 'lean_url', 'reliability', 'reliability_note',
                                     'country', 'event', 'loaded', 'ranks'])
    profiles = df.groupby('agency').agg(
        bias=('bias', 'first'), rated=('rated', 'first'), lean_url=('lean_url', 'first'),
        reliability=('reliability', 'first'), reliability_note=('reliability_note', 'first'), country=('country', 'first'),
        headlines=('agency', 'size'), mood=('event', 'mean'), spice=('loaded', 'mean'))
    profiles = profiles[profiles['headlines'] >= MIN_HEADLINES]

    # Strongest feeling, ranked-choice style (as on the front page and emotions page)
    felt = df.dropna(subset=['ranks'])
    weights = pd.DataFrame([emotion_weights(r) for r in felt['ranks']], index=felt.index).reindex(
        columns=EMOTIONS, fill_value=0).fillna(0)
    feelings = weights.groupby(felt['agency']).mean().drop(columns='neutral')

    framing = framing_scores()
    framing = framing.set_index('agency')['framing'] if not framing.empty else pd.Series(dtype=float)
    edits, _ = find_edits()
    rates = edit_rates(edits)
    rates = rates.set_index('agency')['per_100'] if not rates.empty else pd.Series(dtype=float)

    out = []
    for name, p in profiles.iterrows():
        bias, mood = int(p['bias']), (p['mood'] / 2 if pd.notna(p['mood']) else None)  # event score is -2 to 2
        rated = bool(p['rated'])
        estimated = j2env.globals['lean_estimates'].get(name)
        card = {
            'name': name, 'slug': slug(name), 'bias': bias if rated else None,
            'lean': str(Bias(bias)) if rated else 'Not rated', 'lean_url': p['lean_url'] if rated else None,
            'estimate': str(Bias(estimated)) if estimated is not None else None, 'estimated_bias': estimated,
            'style': chip_style(name, bias), 'color': bias_colors[bias + 3] if rated else '#c8c8d0',
            'reliability': p['reliability'] if isinstance(p['reliability'], str) else None,
            'reliability_note': p['reliability_note'] if isinstance(p['reliability_note'], str) else None,
            'flag': flag(Country(int(p['country']))), 'country': str(Country(int(p['country']))),
            'headlines': int(p['headlines']), 'live': int(live.get(name, 0)),
            'spice': None, 'mood': None, 'framing': None, 'edits': None, 'feeling': None,
        }
        if pd.notna(p['spice']):
            card['spice'] = {'value': round(float(p['spice']), 2), 'badge': spin(p['spice'])}
        if mood is not None:
            card['mood'] = {'value': round(float(mood), 2), 'badge': weather(mood)}
        if name in framing.index:
            card['framing'] = {'value': round(float(framing[name]), 2), 'badge': framing_badge(framing[name])}
        card['edits'] = round(float(rates.get(name, 0.0)), 1)
        if name in feelings.index and feelings.loc[name].max() > 0:
            top = feelings.loc[name].idxmax()
            card['feeling'] = {'emoji': EMOTION_EMOJI[top], 'name': top,
                               'share': round(100 * float(feelings.loc[name, top]))}
        out.append(card)
    return sorted(out, key=lambda c: c['name'].removeprefix('The '))


class AgenciesPage:
    def __init__(self, data: DataHandler):
        self.template = TemplateHandler('agencies.html')
        self.data: DataHandler = data
        self.context = {'title': 'Outlets', 'window_days': WINDOW_DAYS, 'min_headlines': MIN_HEADLINES}

    def generate(self):
        logger.info("Generating agencies page...")
        live = self.data.main_headline_df.groupby('agency').size()
        outlets = outlet_profiles(live)
        self.context['outlets'] = outlets
        # The lineup: outlets in AllSides' five columns from left to right, then the ones it doesn't rate
        self.context['lineup'] = [
            {'name': str(Bias(b)), 'color': bias_colors[b + 3], 'ink': bias_ink[b + 3],
             'outlets': [o for o in outlets if o['bias'] == b or o['estimated_bias'] == b]}
            for b in LEAN.values()
        ] + [{'name': 'Not rated', 'color': '#ffffff', 'ink': '#1f1f2e', 'unrated': True,
              'outlets': [o for o in outlets if o['bias'] is None and o['estimated_bias'] is None]}]
        self.context['lean_quality'] = j2env.globals['lean_quality']
        logger.info("Generating current headlines wordcloud...")
        generate_wordcloud(self.data.main_headline_df[['title', 'agency', 'bias']],
                           PathHandler(PathHandler.FileNames.main_wordcloud).build)
        self.template.write(self.context)
        logger.info("...done")


if __name__ == "__main__":
    Config.set_debug()
    copy_assets()
    dh: DataHandler = DataHandler([DataTypes.agency])
    AgenciesPage(dh).generate()
