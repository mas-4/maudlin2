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
from app.site import boards as strips
from app.site.common import SHARED, TemplateHandler, j2env, motif_href
from app.site.page_motifs import GENRE_EMOJI, GENRE_GLOSS, catalog
from app.utils import get_logger
from app.utils.config import Config

logger = get_logger(__name__)

LEANS = ('left', 'center', 'right')
LEAN_NAME = {'left': 'left', 'center': 'center', 'right': 'right'}
LEAN_INK = {'left': '#3a86ff', 'right': '#ff4f6d', 'center': '#8a8f98'}  # as the shows' chips elsewhere (SHOW_INK)
ANSWER = re.compile(r'answer|counter|mirror|rebut|retort', re.I)  # a related link's note naming a move and its reply
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


# Its claims by who told them (Oct 28: one long list with a chip per show): told on the left | told on the right side by
# side, then both sides, the center, online, fact-checks and voters; each claim's shows as lean-colored dots, their
# names in its hover card. Who it came up with: the shows as one ranked strip, by how many of its claims each told
SIDE_ORDER = ('left', 'right', 'both', 'center', 'online', 'checks', 'voters')
SIDE_HEAD = {'left': ('🫏', 'Told on the left', 'claims heard on left-leaning shows, and no right-leaning one'),
             'right': ('🐘', 'Told on the right', 'claims heard on right-leaning shows, and no left-leaning one'),
             'both': ('⚖️', 'Told on both sides', 'claims heard on left- and right-leaning shows alike'),
             'center': ('🎙️', 'Told in the center', 'claims heard only on center or crossover shows'),
             'online': ('🧶', 'Retold online', 'claims many people posted in their own words'),
             'checks': ('🔎', 'Fact-checked', 'claims a fact-checker examined: the verdict is theirs, behind the link'),
             'voters': ('🗳️', 'Said by voters', 'claims voters made in The Focus Group')}
COLUMN_SHOWN = 25  # claims in a column before "more"
SHOWS_SHOWN = 12  # shows in the strip before "more"
SHOW_LEAN_INK = {'left': '#3a86ff', 'center': '#b8b8c8', 'right': '#ff4f6d', 'crossover': '#8a5cff'}  # boards.LEAN_INK
SHOW_LEAN_EMOJI = {'left': '🫏', 'center': '⚖️', 'right': '🐘', 'crossover': '🔀'}


def side_of(claim: dict) -> str:
    """Which column a claim goes in (SIDE_ORDER), by where it was heard and, on the shows, the shows' leans"""
    src = claim.get('source', '')
    if src == 'shows':
        leans = {t['lean'] for t in claim.get('shows', [])}
        return 'both' if {'left', 'right'} <= leans else 'left' if 'left' in leans else 'right' if 'right' in leans \
            else 'center'
    return 'online' if src == 'narrative' else 'voters' if src == 'Focus Group' else 'checks'


def by_side(claims: list[dict]) -> list[dict]:
    """The claims in their columns, newest first: [{key, emoji, title, sub, claims, more}] for the columns that have
    any, except left and right, which always show (an empty one says so: that's the answer)"""
    cols = {k: [] for k in SIDE_ORDER}
    for c in claims:
        cols[side_of(c)].append(c)
    has_shows = any(cols[k] for k in ('left', 'right', 'both', 'center'))
    out = []
    for k in SIDE_ORDER:
        if not cols[k] and not (k in ('left', 'right') and has_shows):
            continue
        emoji, title, sub = SIDE_HEAD[k]
        items = sorted(cols[k], key=lambda c: str(c.get('date', '')), reverse=True)
        out.append({'key': k, 'emoji': emoji, 'title': title, 'sub': sub, 'claims': items[:COLUMN_SHOWN],
                    'more': items[COLUMN_SHOWN:]})
    return out


def show_strip(claims: list[dict], show_pages: dict) -> list[dict]:
    """The shows its claims came up on, the most claims first, as rows of a board colored by the show's lean"""
    told, meta = defaultdict(set), {}
    for c in claims:
        for t in c.get('shows', []):
            told[t['show']].add(motif_index.key(c['claim']))
            m = meta.setdefault(t['show'], {'lean': t['lean'], 'last': ''})
            m['last'] = max(m['last'], str(t.get('date', ''))[:10])
    top = max((len(v) for v in told.values()), default=0)
    ranked = sorted(told, key=lambda s: (-len(told[s]), s.lower()))
    rows = []
    for s in ranked:
        n, lean = len(told[s]), meta[s]['lean']
        where = f"a {lean}-leaning show" if lean in ('left', 'right') else f"a {lean} show" if lean else 'a show'
        rows.append(strips.row(s, f"show-{show_pages[s]}.html" if s in show_pages else None, n, top,
                               f"{n} claim{'' if n == 1 else 's'}",
                               tip=f"{s}: {where}. {n} of its claims came up here"
                                   + (f", the latest on {meta[s]['last']}" if meta[s]['last'] else '')
                                   + ('. Its page: what it tells most' if s in show_pages else ''),
                               ink=SHOW_LEAN_INK.get(lean, strips.UNCOLORED), mark=SHOW_LEAN_EMOJI.get(lean, '🎙️'),
                               mark_label=where))
    return rows


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


def write_moved(index: dict, shown) -> int:
    """A motif merged into another: its old address goes to the one kept. Written at its own old address, never
    motif_href's: an id without a page falls back to the index there, and the index was overwritten with this redirect
    (Oct 28: bignews.day/motifs went to Not up to the task)"""
    moved = 0
    for old in index['entries'].values():
        if old.get('merged_into') and (to := motif_index.resolve(index, old['id'])) in shown:
            with open(os.path.join(Config.build, f"motif-{old['id'].lower()}.html"), 'w', encoding='utf-8') as f:
                f.write(REDIRECT.format(to=motif_href(to)))
            moved += 1
    return moved


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
            for c in e['claims']:  # all of them: the index's cards no longer list any (Oct 28)
                shows = (s['tellers'].get(motif_index.key(c['claim'])) or single_show(c, s['episodes'])) \
                    if c.get('source') == 'shows' else []
                claims.append({**c, 'shows': [{'show': t['show'], 'lean': t['lean'], 'date': t.get('date', ''),
                                               'url': t.get('url', ''), 'ink': SHOW_LEAN_INK.get(t['lean'], '#ffffff')}
                                              for t in shows]})
            strip = show_strip(claims, show_pages)
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
                'e': e, 'up': up, 'counts': counts, 'sides': by_side(claims), 'related': related(index, e, shown),
                'shows_board': strips.board(
                    'shows', '🎙️', 'Who it came up with', '#ff6b1a',
                    f"the shows we follow where its claims came up ({counts['left']} left-leaning, {counts['center']} "
                    f"center, {counts['right']} right-leaning so far), colored by the show's lean; the bar is how many "
                    "of its claims each one heard", strip[:SHOWS_SHOWN]) if strip else None,
                'shows_more': strips.board('shows-more', '🎙️', f"{len(strip) - SHOWS_SHOWN} more shows", '#ff6b1a',
                                           '', strip[SHOWS_SHOWN:]) if len(strip) > SHOWS_SHOWN else None,
                'lean_key': [{'name': name, 'mark': SHOW_LEAN_EMOJI[k], 'ink': SHOW_LEAN_INK[k]}
                             for k, name in (('left', 'left-leaning'), ('center', 'center'), ('right', 'right-leaning'),
                                             ('crossover', 'crossover'))
                             if any(r['ink'] == SHOW_LEAN_INK[k] for r in strip)],
                'genre_emoji': GENRE_EMOJI, 'genre_gloss': GENRE_GLOSS.get(e['genre'], ''), 'inks': LEAN_INK,
                'news': [labels[sid] for sid in web['motif_stories'].get(e['id'], []) if sid in labels and sid in pages][:NEWS],
                'phrases': phrases,
                'show_pages': show_pages,
            }, os.path.join(Config.build, motif_href(e['id'])))
        moved = write_moved(index, shown)
        logger.info("...%d motif pages, %d moved addresses", len(entries), moved)
