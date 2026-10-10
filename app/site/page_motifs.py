"""The motif index page (#145): our own index of the recurring shapes of today's political rumors and narratives
(app/analysis/motif_index.py), each with the claims filed under it, its genre, its groups and what it rests on, to be
filtered by genre or group and sorted (Oct 10: until then a search and a list by size, so the genres and groups the
person sorts the motifs into weren't to be seen). `catalog()` is shared with Folklore and rumors, which opens on the
index's genres and what's told lately."""
from collections import Counter
from datetime import date, timedelta

from app.analysis import accusations, motif_index
from app.site.common import TemplateHandler
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
    for e in motif_index.live(index):
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


class MotifsPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('motifs.html')

    def generate(self):
        logger.info("Generating motif index page...")
        shown = catalog()
        self.template.write({'title': 'Motif index', **shown,
                             'recurring': sum(1 for e in shown['entries'] if e['count'] > 1),
                             'resting': sum(1 for e in shown['entries'] if e['rests_on'])})
        logger.info("...%d motifs", len(shown['entries']))
