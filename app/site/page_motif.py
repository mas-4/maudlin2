"""A page for each motif (Oct 27, before the site goes on Bluesky and Mastodon): one motif, one link, small enough to
open on a phone (the whole index is one 2.7 MB page). Each shows the motif's note, what it rests on and what rests on
it, the motifs that answer or mirror it, who it came up with on the shows we follow, left, right and center, and its
claims with where each was heard. Same content as the index page (verified motifs, claims through the accusations
screen), arranged around one motif, with a share card of its own.

Which shows a claim came up on is read from the show-claims pipeline's retold groups (app/analysis/show_claims.py):
a show "came up with it" when a claim of the group was heard there, whether the show told it, reported it or argued
against it (tellings don't carry a stance yet), so the page says "came up on", never "told by"."""
import os
import re
from collections import defaultdict

from app.analysis import motif_index, show_claims
from app.site.common import SHARED, TemplateHandler, j2env, motif_href
from app.site.page_motifs import GENRE_EMOJI, GENRE_GLOSS, catalog
from app.utils import get_logger
from app.utils.config import Config

logger = get_logger(__name__)

LEANS = ('left', 'center', 'right')
LEAN_NAME = {'left': 'left', 'center': 'center', 'right': 'right'}
LEAN_INK = {'left': '#3a86ff', 'right': '#ff4f6d', 'center': '#8a8f98'}  # as the shows' chips elsewhere (SHOW_INK)
ANSWER = re.compile(r'answer|counter|mirror|rebut|retort', re.I)  # a related link's note naming a move and its reply
CLAIMS_SHOWN = 40  # claims listed on a motif's page, the newest
TOLD_NOW = 6  # motifs in the front page's strip
NEWS = 10  # stories a motif's page links to, the most told first
PHRASES = 12  # the tellers' own words shown on a motif's page
REDIRECT = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Moved</title>'
            '<link rel="canonical" href="{to}"><meta http-equiv="refresh" content="0; url={to}"></head>'
            '<body><p>This motif is now part of <a href="{to}">this one</a>.</p></body></html>')


def show_tellers() -> dict[str, list[dict]]:
    """claim key -> the show tellings of its retold group: [{show, lean, url, date}], each show once"""
    episodes = show_claims.load()
    out = {}
    for g in show_claims.kept_retold():
        seen, told = set(), []
        for t in g.get('told', []):
            ep = episodes.get(t.get('url'), {})
            show = t.get('show') or ep.get('show')
            if not show or show in seen:
                continue
            seen.add(show)
            told.append({'show': show, 'lean': ep.get('lean') or '', 'date': ep.get('date', ''),
                         'url': t['url'] if str(t.get('url', '')).startswith('http') else ''})
        for claim in [g['claim']] + [t['claim'] for t in g.get('told', []) if t.get('claim')]:
            out.setdefault(motif_index.key(claim), told)
    return out


def single_show(claim: dict, episodes: dict) -> list[dict]:
    """A show claim no retold group holds: the episode its filing came from"""
    ep = episodes.get(claim.get('ref'), {})
    if not ep.get('show'):
        return []
    return [{'show': ep['show'], 'lean': ep.get('lean') or '', 'date': ep.get('date', ''),
             'url': claim['ref'] if str(claim.get('ref', '')).startswith('http') else ''}]


def shared() -> dict:
    """The catalog and the show tellings, worked out once per build and shared by the pages that need them"""
    stamp = j2env.globals.get('build_version')
    if SHARED.get('motif_pages', {}).get('stamp') != stamp:
        index = motif_index.load()
        from app.analysis import motif_web
        SHARED['motif_pages'] = {'stamp': stamp, 'index': index, 'catalog': catalog(index),
                                 'tellers': show_tellers(), 'episodes': show_claims.load(), 'web': motif_web.build()}
    return SHARED['motif_pages']


def came_up(entry: dict, tellers: dict, episodes: dict) -> dict:
    """Who a motif's claims came up with: {left, center, right: [shows]}, people online (claims), fact-checkers"""
    shows = defaultdict(dict)
    posts, checkers = 0, set()
    for c in entry['claims']:
        if c.get('source') == 'shows':
            for t in tellers.get(motif_index.key(c['claim'])) or single_show(c, episodes):
                if t['lean'] in LEANS:
                    shows[t['lean']].setdefault(t['show'], t)
        elif c.get('source') == 'narrative':
            posts += 1
        elif c.get('source') and c.get('source') != 'Focus Group':
            checkers.add(c['source'])
    return {'shows': {k: sorted(shows[k]) for k in LEANS}, 'posts': posts, 'checkers': sorted(checkers),
            'voters': sum(c.get('source') == 'Focus Group' for c in entry['claims'])}


def lean_counts(up: dict) -> dict:
    return {k: len(up['shows'][k]) for k in LEANS}


def related(index: dict, entry: dict, shown: dict) -> list[dict]:
    """The motifs a person linked to this one, among those shown: the answers and mirrors first"""
    notes = index.get('related_notes', {})
    out = []
    for a, b in index.get('related', []):
        if entry['id'] not in (a, b):
            continue
        other = b if a == entry['id'] else a
        if other not in shown:
            continue
        note = notes.get(f'{a}|{b}') or notes.get(f'{b}|{a}') or ''
        out.append({'id': other, 'name': shown[other]['name'], 'note': note, 'answer': bool(ANSWER.search(note))})
    return sorted(out, key=lambda r: (not r['answer'], r['name'].lower()))


def told_now(n: int = TOLD_NOW) -> list[dict]:
    """The front page's strip: the motifs told most in the last days (the index's 'lately'), not the everyday-talk
    genre, each with the shows it came up on by lean"""
    s = shared()
    out = []
    for e in s['catalog']['lately']:
        if e['genre'] == 'Perennials':
            continue
        up = came_up(e, s['tellers'], s['episodes'])
        out.append({'id': e['id'], 'name': e['name'], 'note': e['note'], 'genre': e['genre'],
                    'emoji': GENRE_EMOJI.get(e['genre'], '🧩'), 'recent': e['recent'], 'leans': lean_counts(up),
                    'posts': up['posts']})
        if len(out) == n:
            break
    return out


def page_ids() -> set[str]:
    """The motifs that have a page this build"""
    return {e['id'] for e in shared()['catalog']['entries']}


class MotifPages:
    def __init__(self, dh=None):
        self.template = TemplateHandler('motif.html')

    def generate(self):
        from app.site import share_images
        logger.info("Generating motif pages...")
        s = shared()
        index, entries = s['index'], s['catalog']['entries']
        shown = {e['id']: e for e in entries}
        web = s['web']
        from app.analysis import motif_web
        from app.site.page_story import archived_ids
        labels = {st['id']: st for st in motif_web.stories_around()}
        pages = archived_ids()  # story pages are kept for good once built
        # Its words spotted in headlines and captions were taken off the pages before launch (Oct 27 audit: a quarter
        # to a third were the words used plainly, "Ponzi scheme" in a fraud report, "Game of Thrones" in costumes)
        show_pages = {sh: motif_web.show_slug(sh) for sh in web['shows']}
        for e in entries:
            up = came_up(e, s['tellers'], s['episodes'])
            claims = []
            for c in e['claims'][:CLAIMS_SHOWN]:
                shows = (s['tellers'].get(motif_index.key(c['claim'])) or single_show(c, s['episodes'])) \
                    if c.get('source') == 'shows' else []
                claims.append({**c, 'shows': [{**t, 'ink': LEAN_INK.get(t['lean'], '#b8b8c8')} for t in shows]})
            counts = lean_counts(up)
            phrases = [ph for ph, _ in motif_index.carrying(index['entries'][e['id']])][:PHRASES]
            try:
                image = share_images.motif_card(e['name'], e['note'], e['genre'], counts, phrases[0] if phrases else None)
            except Exception as err:  # noqa: BLE001 - the page stands without its card
                logger.warning("Motif %s: share card: %s", e['id'], err)
                image = None
            self.template.write({
                'title': e['name'], 'og_title': f"{e['name']} · BND Motif Index",
                'og_description': (e['note'] or 'A shape a story takes, in our motif index.') +
                                  ' A story people tell, not a claim that it is true.',
                'og_image': image, 'og_image_alt': f"{e['name']}: {e['note']}",
                'e': e, 'up': up, 'counts': counts, 'claims': claims, 'related': related(index, e, shown),
                'genre_emoji': GENRE_EMOJI, 'genre_gloss': GENRE_GLOSS.get(e['genre'], ''), 'inks': LEAN_INK,
                'news': [labels[sid] for sid in web['motif_stories'].get(e['id'], []) if sid in labels and sid in pages][:NEWS],
                'phrases': phrases,
                'show_pages': show_pages,
            }, os.path.join(Config.build, motif_href(e['id'])))
        # A motif merged into another: its old address goes to the one kept
        moved = 0
        for old in index['entries'].values():
            if old.get('merged_into') and (to := motif_index.resolve(index, old['id'])) in shown:
                with open(os.path.join(Config.build, motif_href(old['id'])), 'w', encoding='utf-8') as f:
                    f.write(REDIRECT.format(to=motif_href(to)))
                moved += 1
        logger.info("...%d motif pages, %d moved addresses", len(entries), moved)
