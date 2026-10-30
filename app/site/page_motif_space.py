"""Motif space (Oct 30, the person: "we should make *this* public on the folklore page"): the motif index laid out by
meaning (app/analysis/motif_space.py), drawn by static/motif_space.js. Only the public layer goes in: the motifs the
site shows (page_motifs.catalog: verified by a person) and their claims as the accusations screen lets them through,
the same as the index page already shows. The layout is worked out once a day from that layer; every build joins it to
the index and the screen as they stand then, so a claim held or a motif dropped since leaves the page at once."""
from app.analysis import accusations, motif_index, motif_space
from app.site.common import TemplateHandler, motif_href
from app.site.page_motifs import GENRE_EMOJI, catalog
from app.utils import get_logger

logger = get_logger(__name__)


def public_entries(index: dict | None = None, screen=None) -> list[dict]:
    """The site's motifs with their claims for motif_space.layout: each claim's text as embedded (the index's own)
    and as shown (corrected and screened); claims the screen holds are left out"""
    index = index if index is not None else motif_index.load()
    own = screen is None
    screen = screen or accusations.screen()
    shown = catalog(index, screen)
    out = []
    for m in shown['entries']:
        e = index['entries'][m['id']]
        claims = []
        for c in motif_index.public_claims(e):
            text = screen.shown(motif_index.corrected(c['claim'], index), c.get('source', ''))
            if text:
                claims.append({'text': c['claim'], 'shown': text, 'ok': True})
        if claims:
            out.append({'id': m['id'], 'name': m['name'], 'note': m['note'], 'genre': m['genre'],
                        'groups': [g['id'] for g in m['groups']], 'rests': [p['id'] for p in m['rests_on']],
                        'claims': claims})
    if own:
        screen.save()
    return out


def join(data: dict, entries: list[dict], index: dict) -> tuple[dict, int]:
    """The day's layout joined to the motifs and claims as they are now: motifs the site no longer shows and claims no
    longer shown are dropped, names, notes, genres and claim texts are today's. Returns (the page's data, how many
    motifs shown now have no place yet)"""
    now = {e['id']: e for e in entries}
    shown = {motif_space.key(c['text']): c['shown'] for e in entries for c in e['claims']}
    keep = [i for i, m in enumerate(data['motifs']) if m['id'] in now and m.get('xy')]
    new = {old: n for n, old in enumerate(keep)}
    motifs = []
    for old in keep:
        m, e = data['motifs'][old], now[data['motifs'][old]['id']]
        motifs.append({'id': m['id'], 'name': e['name'], 'note': e['note'], 'genre': e['genre'], 'groups': e['groups'],
                       'href': motif_href(m['id']), 'xy': m['xy'], **({'xyz': m['xyz']} if m.get('xyz') else {}),
                       'spread': m.get('spread'),
                       'near': {s: [[new[j], v] for j, v in near if j in new] for s, near in m.get('near', {}).items()}})
    at = {m['id']: n for n, m in enumerate(motifs)}
    for m in motifs:
        m['rests'] = [at[p] for p in now[m['id']]['rests'] if p in at]
    claims = []
    for c in data['claims']:
        if c['k'] not in shown:
            continue
        ms = [[new[i], ok, d] for i, ok, d in c['m'] if i in new]
        if ms:
            claims.append({'t': shown[c['k']], 'xy': c['xy'], 'm': ms, **({'xyz': c['xyz']} if c.get('xyz') else {})})
    related = [[at[a], at[b]] for a, b in (tuple(p) for p in index.get('related', []) if len(p) == 2)
               if a in at and b in at]
    groups = {g: v.get('name', g) for g, v in index.get('groups', {}).items()}
    every = motif_index.facet_values(index).get('genre', [])  # the site's genre order, then any newer one
    out = {'public': True, 'spaces': data['spaces'], 'motifs': motifs, 'claims': claims, 'related': related,
           'regions': {s: [r for r in rs if r['group'] in groups] for s, rs in data.get('regions', {}).items()},
           'groups': groups, 'genres': [g for g in GENRE_EMOJI if g in every] + [g for g in every if g not in GENRE_EMOJI]}
    return out, sum(1 for i in now if i not in at)


class MotifSpacePage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('motif_space.html', 'motif-space.html')
        self.context = {'title': 'Motif space',
                        'og_description': 'Every motif in our index, placed by what its claims say: similar stories sit close together.'}

    def generate(self):
        logger.info("Generating the motif space page...")
        index = motif_index.load()
        entries = public_entries(index)
        data = motif_space.today(entries)
        if not data or not data.get('motifs'):
            logger.warning("Motif space: no layout, page not written")
            return
        page, missing = join(data, entries, index)
        self.context.update({'data': page, 'day': data.get('day', ''), 'missing': missing})
        self.template.write(self.context)
        logger.info("...done (%d motifs, %d claims)", len(page['motifs']), len(page['claims']))
