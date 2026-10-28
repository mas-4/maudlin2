"""The motif index page (#145): our own index of the recurring shapes of today's political rumors and narratives
(app/analysis/motif_index.py), each with the claims filed under it, its genre, its groups and what it rests on, to be
filtered by genre or group and sorted (Oct 10: until then a search and a list by size, so the genres and groups the
person sorts the motifs into weren't to be seen). `catalog()` is shared with Folklore and rumors, which opens on the
index's genres and what's told lately."""
from collections import Counter
from datetime import date, timedelta

from markupsafe import Markup, escape

from app.analysis import accusations, motif_index
from app.site import motif_search
from app.site.boards import GENRE_INK, UNCOLORED
from app.site.common import TemplateHandler, motif_href
from app.utils import get_logger

logger = get_logger(__name__)

# One emoji per genre, the same everywhere (docs/style-book.md)
GENRE_EMOJI = {'Archetypes': '🎭', 'Plots': '📜', 'Beliefs': '🪨', 'Theories': '🕵️', 'Arguments': '🗣️',
               'Values': '⚖️', 'Exhortations': '📣', 'Perennials': '🌻'}
# What each genre is, for readers: the "What it is" and quick test of docs/motif-praxis.md (the person's own genre
# notes, index['facet_notes'], are written for sorting, not for readers: Perennials' runs to a paragraph of rules)
GENRE_GLOSS = {
    'Archetypes': 'A kind of person tellers portray: "a [type of person] who…"',
    'Plots': 'What happened: an event or a sequence, "X happens, then Y"',
    'Beliefs': 'A premise people reason from, what comes before "so…"',
    'Theories': 'An account people reason to: the hidden cause, agent or mechanism, the "because…"',
    'Arguments': 'A rhetorical move people actually make: "people argue by…"',
    'Values': 'How things ought to be: "X should be…"',
    'Exhortations': 'A call to act: "we should do X"',
    'Perennials': 'A safe topic shared for its own sake, which strangers can talk about without taking a side',
}
LATELY_DAYS = 3  # "told lately": claims dated in the last few days (filing began Oct 5, so a week was nearly all of it)
SHELF_TOP = 4  # motifs shown on a genre's shelf, the biggest
LATELY_TOP = 15


def catalog(index: dict | None = None, screen: accusations.Screen | None = None) -> dict:
    """The verified motifs as the site shows them, with their claims as the accusations screen lets them through:
    {entries (most claims first), genres (the praxis's order, each with its gloss and biggest motifs), groups (most
    motifs first), claims, lately (most told in the last LATELY_DAYS)}"""
    index = index if index is not None else motif_index.load()
    own_screen = screen is None
    screen = screen or accusations.screen()  # claims accusing a named private person of a crime: name swapped out, or held
    since = (date.today() - timedelta(days=LATELY_DAYS - 1)).isoformat()
    groups = index.get('groups', {})
    entries = {}
    bins = motif_index.watched(index)  # watch lists (Straight news): sinks for plain reports, not shapes to show
    for e in motif_index.live(index):
        if e['id'] in bins:
            continue
        claims = motif_index.public_claims(e) if motif_index.public(e) else []  # only motifs a person verified
        claims = [{**c, 'claim': shown} for c in claims
                  if (shown := screen.shown(motif_index.corrected(c['claim'], index), c.get('source', '')))]
        if not claims:
            continue
        sources = Counter('people online' if c.get('source') == 'narrative' else c.get('source', '') for c in claims)
        entries[e['id']] = {**e, 'note': motif_index.public_note(e), 'count': len(claims), 'sources': sources.most_common(),
                            'claims': sorted(claims, key=lambda c: c.get('date', ''), reverse=True),
                            'recent': sum(c.get('date', '') >= since for c in claims),
                            'genre': motif_index.person_genre(e) or '',
                            'groups': [{'id': g, 'name': groups[g]['name']} for g in motif_index.person_groups(e) if g in groups]}
    for m in entries.values():  # what it rests on, and what rests on it, among the motifs shown
        m['rests_on'] = [{'id': p, 'name': entries[p]['name']} for p in motif_index.parents_of(m) if p in entries]
        m['under'] = []
    for m in entries.values():
        for p in m['rests_on']:
            entries[p['id']]['under'].append({'id': m['id'], 'name': m['name']})
    ordered = sorted(entries.values(), key=lambda e: (-e['count'], e['id']))
    genres = []
    every = motif_index.facet_values(index).get('genre', [])  # in the praxis's order, then any newer genre
    for g in [g for g in GENRE_EMOJI if g in every] + [g for g in every if g not in GENRE_EMOJI]:
        held = [e for e in ordered if e['genre'] == g]
        if held:
            genres.append({'name': g, 'emoji': GENRE_EMOJI.get(g, '🧩'), 'about': GENRE_GLOSS.get(g, ''),
                           'count': len(held), 'claims': sum(e['count'] for e in held), 'top': held[:SHELF_TOP]})
    sizes = Counter(g['id'] for e in ordered for g in e['groups'])
    shelves = sorted(({'id': gid, 'name': groups[gid]['name'], 'note': groups[gid].get('note', ''), 'count': n}
                      for gid, n in sizes.items() if n >= 2), key=lambda g: (-g['count'], g['name'].lower()))
    if own_screen:
        screen.save()
    return {'entries': ordered, 'genres': genres, 'groups': shelves, 'claims': sum(e['count'] for e in ordered),
            'lately': sorted((e for e in ordered if e['recent']), key=lambda e: (-e['recent'], -e['count']))[:LATELY_TOP],
            'lately_days': LATELY_DAYS, 'genre_emoji': GENRE_EMOJI}


# The index's slim cards (Oct 28: 958 cards each with up to 10 claims and a sentence of sources, a masonry wall): a
# card is the name, the note, where its claims were heard as one bar, and three weeks of its claims as a sparkline;
# its claims and sources go in its hover card, and all of them on its page. The bar's parts, in this fixed order:
MIX = [('left', '🫏', 'left-leaning shows', '#3a86ff'), ('center', '⚖️', 'center shows', '#b8b8c8'),
       ('right', '🐘', 'right-leaning shows', '#ff4f6d'), ('crossover', '🔀', 'crossover shows', '#8a5cff'),
       ('online', '🧶', 'people online', '#00c2a8'), ('checks', '🔎', 'fact-checkers', '#ffc400'),
       ('voters', '🗳️', 'voters in The Focus Group', '#1f1f2e')]
SPARK_DAYS = 21
SPARK_W, SPARK_H = 80, 22
HOVER_CLAIMS = 8  # claims in a card's hover card, the newest; all of them on its page
HOVER_CHARS = 220


def tellers_now() -> tuple[dict, dict]:
    """The show tellings by claim and the show episodes (page_motif.shared's, when this build has worked them out
    already, as Folklore and rumors does before this page)"""
    from app.analysis import show_claims
    from app.site import page_motif
    from app.site.common import SHARED, j2env
    s = SHARED.get('motif_pages')
    if s and s.get('stamp') == j2env.globals.get('build_version'):
        return s['tellers'], s['episodes']
    return page_motif.show_tellers(), show_claims.load()


def mix(entry: dict, tellers: dict, episodes: dict) -> list[dict]:
    """Where a motif's claims were heard, as tellings: a claim told on a show counts once for each show (by the show's
    lean), once if retold online, once for its fact-check, once from voters. [{key, emoji, name, ink, n, pct}] in MIX
    order, the parts it has"""
    from app.site.page_motif import single_show
    n = Counter()
    for c in entry['claims']:
        src = c.get('source', '')
        if src == 'shows':
            for t in tellers.get(motif_index.key(c['claim'])) or single_show(c, episodes):
                n[t['lean'] if t['lean'] in ('left', 'center', 'right', 'crossover') else 'center'] += 1
        elif src == 'narrative':
            n['online'] += 1
        elif src == 'Focus Group':
            n['voters'] += 1
        elif src:
            n['checks'] += 1
    total = sum(n.values()) or 1
    return [{'key': k, 'emoji': em, 'name': name, 'ink': ink, 'n': n[k], 'pct': max(1, round(100 * n[k] / total))}
            for k, em, name, ink in MIX if n[k]]


def sparkline(entry: dict, today: date | None = None) -> Markup:
    """Its claims a day over the last SPARK_DAYS days, as a little filled line (inline SVG, nothing to load)"""
    today = today or date.today()
    days = [(today - timedelta(days=SPARK_DAYS - 1 - i)).isoformat() for i in range(SPARK_DAYS)]
    per = Counter(str(c.get('date', ''))[:10] for c in entry['claims'])
    counts = [per[d] for d in days]
    top = max(counts) or 1
    step = SPARK_W // (SPARK_DAYS - 1)
    line = ' '.join(f'{i * step},{round(SPARK_H - 2 - (SPARK_H - 4) * v / top)}' for i, v in enumerate(counts))
    total = sum(counts)
    label = f"{total} claim{'' if total == 1 else 's'} in the last three weeks, at most {max(counts)} a day"
    w = step * (SPARK_DAYS - 1)
    return Markup(f'<svg class="motif-slim-spark" viewBox="0 0 {w} {SPARK_H}" width="{w}" height="{SPARK_H}" '
                  f'role="img" aria-label="{escape(label)}"><path d="M0,{SPARK_H}L{line}L{w},{SPARK_H}Z"/>'
                  f'<polyline points="{line}"/></svg>')


def hover(entry: dict, parts: list[dict]) -> dict:
    """What a card's hover card shows: its newest claims with where each was heard, the sources sentence, what it rests
    on and what rests on it, its groups, its dates. Short keys: one of these per motif goes in the page"""
    def heard(c):
        src = c.get('source', '')
        return 'people online' if src == 'narrative' else 'voters in The Focus Group' if src == 'Focus Group' \
            else 'on the shows' if src == 'shows' else src
    claims = [[c['claim'] if len(c['claim']) <= HOVER_CHARS else c['claim'][:HOVER_CHARS - 1].rstrip() + '…',
               heard(c), c['ref'] if c.get('source') != 'narrative' and str(c.get('ref', '')).startswith('http') else '']
              for c in entry['claims'][:HOVER_CLAIMS]]
    return {'c': claims, 'm': max(0, entry['count'] - HOVER_CLAIMS),
            's': ', '.join(f"{s}{f' ×{n}' if n > 1 else ''}" for s, n in entry['sources']),
            'x': [f"{p['emoji']} {p['n']} {p['name']}" for p in parts],
            'r': [[motif_href(p['id']), p['name']] for p in entry['rests_on']],
            'u': [[motif_href(p['id']), p['name']] for p in entry['under']],
            'g': [g['name'] for g in entry['groups']],
            'd': f"{entry['id']} · first seen {entry.get('first_seen') or '?'}"
                 + (f" · last {entry['last_seen']}" if entry.get('last_seen') and entry['last_seen'] != entry.get('first_seen') else '')}


class MotifsPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('motifs.html')

    def generate(self):
        logger.info("Generating motif index page...")
        index = motif_index.load()
        shown = catalog(index)
        size = motif_search.write(shown['entries'], index)  # what the page's search box fetches on first use
        logger.info("...search index: %d motifs, %d KB", len(shown['entries']), size // 1024)
        try:
            tellers, episodes = tellers_now()
        except Exception as e:  # noqa: BLE001 - the shows' leans are extra: without them the shows count as center
            logger.warning("Motif index: no show tellings (%s)", e)
            tellers, episodes = {}, {}
        slim = {}
        for e in shown['entries']:
            parts = mix(e, tellers, episodes)
            slim[e['id']] = {'mix': parts, 'spark': sparkline(e), 'ink': GENRE_INK.get(e['genre'], UNCOLORED)}
        self.template.write({'title': 'Motif index', **shown, 'search_file': motif_search.FILE,
                             'slim': slim, 'hover': {e['id']: hover(e, slim[e['id']]['mix']) for e in shown['entries']},
                             'mix_key': [{'name': name, 'mark': em, 'ink': ink} for _, em, name, ink in MIX],
                             'genre_inks': GENRE_INK,
                             'recurring': sum(1 for e in shown['entries'] if e['count'] > 1),
                             # the headline: shapes told about two events or more (motif_told.py), the rest placed
                             'attested': sum(1 for e in shown['entries'] if motif_index.attested(e)),
                             'resting': sum(1 for e in shown['entries'] if e['rests_on'])})
        logger.info("...%d motifs", len(shown['entries']))
