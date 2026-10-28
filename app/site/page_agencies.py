"""The outlets page: every outlet we follow and how it covers the news (how loaded its wording is, how grim it makes
the news, how it frames shared stories against everyone else, how often it rewrites headlines, how much wire copy it
runs, the feeling its headlines stir most). All from the last WINDOW_DAYS of news headlines.

Oct 28 (the site redo): it was a lineup of chips in five lean columns and ~150 masonry cards of badges. Now paired
leaderboards come first (Spiciest | Plainest, Grimmest | Sunniest, Most rewrites | Never rewrites, Most wire copy |
Least), each row colored by the outlet's type on the outlet map (named for what outlets do, not their lean), the lean
a small mark beside the name; then every outlet in one sortable table with inline bars. Each card's blurb and badges
went into the hover card on the outlet's name."""
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz

from app.analysis import outlet_profile
from app.site import boards, wiki
from app.site.page_outlet_map import LEAN_MARK, OFF_MAP, type_key, type_look
from app.site.page_outlets import OutletPages
from app.analysis.edits import find_edits, edit_rates
from app.analysis.wire import wire_share, WIRES
from app.analysis.newsfilter import EMOTION_EMOJI, EMOTIONS, emotion_weights
from app.analysis.stories import framing_scores
from app.models import Session, Agency, Article, Headline
from app.site.common import chip_style, copy_assets, j2env, short_name, TemplateHandler, PathHandler
from app.site.favicons import slug
from app.site.data import DataHandler, DataTypes, NEWS_ONLY
from app.site.graphing import bias_colors
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
    # The scores are whole numbers (loaded 0 plain to 2 built to provoke; event -2 grim to 2 upbeat): the boards rank
    # outlets by the share of their headlines on each side, which reads plainer than an average
    for col, src, test in (('stirs', 'loaded', lambda v: v >= 1), ('plain', 'loaded', lambda v: v == 0),
                           ('grim', 'event', lambda v: v < 0), ('sunny', 'event', lambda v: v > 0)):
        df[col] = test(df[src]).astype(float).where(df[src].notna())
    profiles = df.groupby('agency').agg(
        bias=('bias', 'first'), rated=('rated', 'first'), lean_url=('lean_url', 'first'),
        reliability=('reliability', 'first'), reliability_note=('reliability_note', 'first'), country=('country', 'first'),
        headlines=('agency', 'size'), mood=('event', 'mean'), spice=('loaded', 'mean'),
        stirs=('stirs', 'mean'), plain=('plain', 'mean'), grim=('grim', 'mean'), sunny=('sunny', 'mean'))
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
    wire = wire_share()

    out = []
    background = wiki.all_info()
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
            'wiki': background.get(name),
            'shares': {k: (round(100 * float(p[k])) if pd.notna(p[k]) else None)
                       for k in ('stirs', 'plain', 'grim', 'sunny')},
        }
        if pd.notna(p['spice']):
            card['spice'] = {'value': round(float(p['spice']), 2), 'badge': spin(p['spice'])}
        if mood is not None:
            card['mood'] = {'value': round(float(mood), 2), 'badge': weather(mood)}
        if name in framing.index:
            card['framing'] = {'value': round(float(framing[name]), 2), 'badge': framing_badge(framing[name])}
        card['edits'] = round(float(rates.get(name, 0.0)), 1)
        # Share of its headlines that are AP or Reuters copy (None for the wires themselves, or too few headlines)
        card['wire'] = round(100 * float(wire.loc[name, 'share'])) if name in wire.index else None
        card['is_wire'] = name in WIRES
        if name in feelings.index and feelings.loc[name].max() > 0:
            top = feelings.loc[name].idxmax()
            card['feeling'] = {'emoji': EMOTION_EMOJI[top], 'name': top,
                               'share': round(100 * float(feelings.loc[name, top]))}
        out.append(card)
    return sorted(out, key=lambda c: c['name'].removeprefix('The '))


BOARD_ROWS = 10


def lean_look(o: dict) -> dict:
    """An outlet's lean as the small mark beside its name: AllSides' rating, else our estimate (dashed), else none"""
    b = o['bias'] if o['bias'] is not None else o['estimated_bias']
    if b is None:
        return {'mark': '', 'ink': '#ffffff', 'label': 'not rated', 'est': True, 'order': 9}
    word = str(Bias(b)).lower()
    return {'mark': LEAN_MARK[b], 'ink': bias_colors[b + 3], 'est': o['bias'] is None, 'order': b,
            'label': f'{word}, our estimate' if o['bias'] is None else f'{word} (AllSides)'}


def mark_types(outlets: list[dict], profile: dict) -> None:
    """Each outlet's type on the outlet map (the boards' colors) and its lean mark"""
    mapped = (profile or {}).get('outlets', {})
    for o in outlets:
        o['look'] = type_look(mapped.get(o['name']))
        o['lean_look'] = lean_look(o)


def outlet_boards(outlets: list[dict], window_days: int) -> list[list[dict]]:
    """The four answering pairs of leaderboards, each row colored by the outlet's type"""
    def rows(items, value, figure, tip):
        items = list(items)[:BOARD_ROWS]
        top = max((value(o) for o in items), default=0)
        out = []
        for o in items:
            r = boards.row(short_name(o['name']), f"outlet-{o['slug']}.html", value(o), top, figure(o), tip=tip(o),
                           ink=o['look']['ink'], mark=o['look']['mark'], mark_label=o['look']['name'])
            r.update({'lean': o['lean_look'], 'card': o['slug']})
            out.append(r)
        return out

    def share(key):
        return [o for o in outlets if o['shares'][key] is not None]
    pct = lambda key: lambda o: f"{o['shares'][key]}%"  # noqa: E731
    no_tip = lambda o: ''  # noqa: E731 - the outlet's own card shows on hover
    days = f'{window_days} days'
    wired = [o for o in outlets if o['wire'] is not None]
    pairs = [
        (boards.board('spiciest', '🌶️', 'Spiciest', '#ff6b1a', 'the bar is the share of its headlines worded to '
                      'stir: loaded words, or built to provoke',
                      rows(sorted(share('stirs'), key=lambda o: -o['shares']['stirs']), lambda o: o['shares']['stirs'],
                           pct('stirs'), no_tip)),
         boards.board('plainest', '🍞', 'Plainest', '#c8b89a', 'the bar is the share of its headlines in plain words',
                      rows(sorted(share('plain'), key=lambda o: -o['shares']['plain']), lambda o: o['shares']['plain'],
                           pct('plain'), no_tip))),
        (boards.board('grimmest', '⛈️', 'Grimmest', '#8a5cff', 'the bar is the share of its headlines that tell bad '
                      'news: harm, loss, danger',
                      rows(sorted(share('grim'), key=lambda o: -o['shares']['grim']), lambda o: o['shares']['grim'],
                           pct('grim'), no_tip)),
         boards.board('sunniest', '☀️', 'Sunniest', '#ffc400', 'the bar is the share of its headlines that tell good '
                      'news', rows(sorted(share('sunny'), key=lambda o: -o['shares']['sunny']),
                                   lambda o: o['shares']['sunny'], pct('sunny'), no_tip))),
        (boards.board('rewrites', '✏️', 'Most rewrites', '#00c2a8', 'the bar is how many of its headlines it '
                      'changed after we first saw them, per 100',
                      rows(sorted((o for o in outlets if o['edits']), key=lambda o: -o['edits']), lambda o: o['edits'],
                           lambda o: f"{o['edits']:g} per 100", no_tip)),
         boards.board('never', '🪨', 'Never rewrites', '#a9a9b8', f'changed none of its headlines in {days}; the bar '
                      'is how many it ran, the busiest first',
                      rows(sorted((o for o in outlets if not o['edits']), key=lambda o: -o['headlines']),
                           lambda o: o['headlines'], lambda o: f"{o['headlines']:,} headlines", no_tip),
                      empty='🦗 Every outlet rewrote something this month.')),
        (boards.board('wire', '📡', 'Most wire copy', '#3fb8af', 'the bar is the share of its headlines that are AP '
                      'or Reuters headlines, word for word or nearly',
                      rows(sorted(wired, key=lambda o: -o['wire']), lambda o: o['wire'], lambda o: f"{o['wire']}%",
                           no_tip)),
         boards.board('own', '🖋️', 'Least wire copy', '#ff4fa3', f'the least AP and Reuters copy first; the bar is '
                      f'how many headlines it ran in {days}, the busiest first among equals',
                      rows(sorted(wired, key=lambda o: (o['wire'], -o['headlines'])), lambda o: o['headlines'],
                           lambda o: f"{o['wire']}% of {o['headlines']:,}", no_tip))),
    ]
    return [list(p) for p in pairs]


def medians(outlets: list[dict]) -> dict:
    """The median outlet's figures, for each outlet page to compare its own with"""
    def med(values):
        values = sorted(v for v in values if v is not None)
        return values[len(values) // 2] if values else None
    return {'stirs': med(o['shares']['stirs'] for o in outlets), 'grim': med(o['shares']['grim'] for o in outlets),
            'edits': med(o['edits'] for o in outlets), 'wire': med(o['wire'] for o in outlets if not o['is_wire']),
            'outlets': len(outlets)}


def table_tops(outlets: list[dict]) -> dict:
    """Each table column's biggest figure, for its inline bars"""
    return {'stirs': max((o['shares']['stirs'] or 0 for o in outlets), default=0) or 1,
            'grim': max((o['shares']['grim'] or 0 for o in outlets), default=0) or 1,
            'edits': max((o['edits'] or 0 for o in outlets), default=0) or 1,
            'wire': max((o['wire'] or 0 for o in outlets), default=0) or 1}


class AgenciesPage:
    def __init__(self, data: DataHandler):
        self.template = TemplateHandler('agencies.html')
        self.data: DataHandler = data
        self.context = {'title': 'Outlets', 'window_days': WINDOW_DAYS, 'min_headlines': MIN_HEADLINES}

    def generate(self):
        logger.info("Generating agencies page...")
        live = self.data.main_headline_df.groupby('agency').size()
        outlets = outlet_profiles(live)
        try:
            profile = outlet_profile.profiles()  # the outlet map's types color the boards (cached for the day)
        except Exception:  # noqa: BLE001 - boards without types beat no page
            logger.exception("Outlet profiles failed; the outlets page goes without types this build")
            profile = {}
        mark_types(outlets, profile)
        self.context['outlets'] = outlets
        self.context['pairs'] = outlet_boards(outlets, WINDOW_DAYS)
        self.context['type_key'] = type_key({o['look']['name'] for o in outlets},
                                            off_map=any(o['look'] is OFF_MAP for o in outlets))
        self.context['tops'] = table_tops(outlets)
        self.context['lean_quality'] = j2env.globals['lean_quality']
        OutletPages(self.data, outlets, WINDOW_DAYS, medians(outlets), self.context['tops']).generate()  # one page per outlet (#126)
        logger.info("Generating current headlines wordcloud...")
        generate_wordcloud(self.data.main_headline_df[['title', 'agency', 'bias']],
                           PathHandler(PathHandler.FileNames.main_wordcloud).build)
        self.template.write(self.context)
        logger.info("...done")


if __name__ == "__main__":
    Config.set_debug()
    from app.builder import prepare
    prepare()  # icons, ratings and lean estimates, as in a full build
    copy_assets()
    dh: DataHandler = DataHandler([DataTypes.agency])
    AgenciesPage(dh).generate()
