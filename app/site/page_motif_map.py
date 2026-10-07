"""The motif map: the motif index (app/analysis/motif_index.py) drawn as a map, each verified motif a dot sized by its
claims, joined to its kinds (a kind of a broader motif), to the motifs a person marked related, and to motifs that
share a claim; a person's groups drawn as colored areas around their motifs, a dot's fill its genre. The checker's map
(scripts/checker) is the private working copy, where motifs are moved and joined; this one only shows what the motifs
page shows: motifs a person verified, and their claims as the accusations screen lets them through. Both draw through
static/motif-map-layout.js (where groups sit, their blobs, the colors), so they look alike."""
import json
from collections import defaultdict
from itertools import combinations

from app.analysis import accusations, motif_index
from app.site.common import TemplateHandler
from app.utils import get_logger

logger = get_logger(__name__)

CLAIMS_SHOWN = 6  # claims in a motif's card, the newest


def graph(index: dict | None = None, screen: accusations.Screen | None = None) -> dict:
    """{motifs, links, groups, genres} for the map: verified motifs only, links only between two of them; groups and
    genres A to Z, each with its place among all of them (k), which picks its color as on the checker"""
    index = index if index is not None else motif_index.load()
    screen = screen or accusations.screen()
    motifs, holders = {}, defaultdict(set)
    for e in motif_index.live(index):
        if not motif_index.public(e):
            continue
        claims = [{**c, 'claim': shown} for c in motif_index.public_claims(e)
                  if (shown := screen.shown(motif_index.corrected(c['claim'], index), c['source']))]
        if not claims:
            continue
        for c in claims:
            holders[motif_index.key(c['claim'])].add(e['id'])
        claims.sort(key=lambda c: c.get('date', ''), reverse=True)
        motifs[e['id']] = {
            'id': e['id'], 'name': e['name'], 'note': motif_index.public_note(e), 'count': len(claims),
            'first': e.get('first_seen', ''), 'groups': motif_index.groups_of(e),
            'genre': (e.get('facets') or {}).get('genre', ''),
            'claims': [{'claim': c['claim'], 'source': 'people online' if c['source'] == 'narrative' else c['source'],
                        'url': c.get('ref', '') if c['source'] not in ('narrative',) and str(c.get('ref', '')).startswith('http') else ''}
                       for c in claims[:CLAIMS_SHOWN]]}
    links, seen = [], set()
    for m in motifs.values():
        for p in motif_index.parents_of(index['entries'][m['id']]):
            if p in motifs:
                links.append({'source': m['id'], 'target': p, 'kind': 'kind'})
                seen.add(frozenset((m['id'], p)))
    for pair in index.get('related', []):
        a, b = (motif_index.resolve(index, x) for x in pair)
        if a in motifs and b in motifs and a != b and frozenset((a, b)) not in seen:
            links.append({'source': a, 'target': b, 'kind': 'related'})
            seen.add(frozenset((a, b)))
    shared = defaultdict(int)
    for ids in holders.values():
        for a, b in combinations(sorted(ids), 2):
            shared[(a, b)] += 1
    for (a, b), n in shared.items():
        if frozenset((a, b)) not in seen:
            links.append({'source': a, 'target': b, 'kind': 'shared', 'n': n})
    groups = []
    for k, g in enumerate(sorted(index.get('groups', {}).values(), key=lambda g: g['name'].lower())):
        members = [m for m in motifs.values() if g['id'] in m['groups']]
        if len(members) >= 2:
            groups.append({'id': g['id'], 'name': g['name'], 'k': k, 'size': len(members)})
    every = motif_index.facet_values(index).get('genre', [])  # only the ones used here go out, with their place (k)
    genres = [{'name': v, 'k': k, 'size': n} for k, v in enumerate(every)
              if (n := sum(m['genre'] == v for m in motifs.values()))]
    # a dot's outline: broad (a kind with kinds of its own), sub (a kind of a broader one), or both, in a chain
    for m in motifs.values():
        m['broad'] = any(link['target'] == m['id'] and link['kind'] == 'kind' for link in links)
        m['sub'] = any(link['source'] == m['id'] and link['kind'] == 'kind' for link in links)
    screen.save()
    return {'motifs': sorted(motifs.values(), key=lambda m: m['name'].lower()), 'links': links, 'groups': groups,
            'genres': genres}


class MotifMapPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('motif_map.html', 'motif-map.html')

    def generate(self):
        logger.info("Generating motif map...")
        g = graph()
        self.template.write({'title': 'Motif map', 'data': json.dumps(g, ensure_ascii=False).replace('</', '<\\/'),
                             'motifs': len(g['motifs']), 'groups': g['groups'], 'genres': g['genres'],
                             'kinds': sum(m['broad'] for m in g['motifs']),
                             'links': len(g['links'])})
        logger.info("...%d motifs, %d links", len(g['motifs']), len(g['links']))
