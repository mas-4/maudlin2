"""Folklore and rumors (work in progress, #142, #153): one catalog of what's told, from three sources (Oct 8; until
then Folklore and Rumors were two pages). A card per claim:
- retold online: the folklore-shaped narratives in what people say on Bluesky and Mastodon, from the latest nightly
  report (app/narratives.py), with how many people tell it, how varied their wording is, and the news it rides on;
- told on the shows: claims told on two or more of the podcasts, call-in and video shows we transcribe
  (app/analysis/show_claims.py), with which shows;
- fact-checked: the rumors fact-checkers examined in the last few weeks (app/analysis/factchecks.py); the verdict
  is always the fact-checker's own, behind its link. A check already linked from a narrative's card isn't repeated.
The page opens on the motif index itself (Oct 10: it had shown only the motifs on today's cards): its genres, the
motifs told most lately and its groups, from page_motifs.catalog. Each card carries the motifs it's filed under in
our motif index, and the person's genres of those motifs.

People's own posts are never shown on the published site, only the model's summary of what they share: even without
handles, a quoted post can be searched back to its author. Local preview builds (debug) show a few versions, so the
research can be checked."""
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from app.analysis.rumor_shapes import CONSPIRACY_SCOPES, EMOJI as SHAPE_EMOJI, RUMOR_CLASSES
from app import bluesky_examples
from app.analysis import accusations, circulation, factchecks, motif_index, narrative_threads, show_claims
from app.site import boards as strips
from app.site.common import TemplateHandler, motif_href
from app.site.page_motifs import GENRE_EMOJI, catalog
from app.utils import Config, get_logger

# The reports' reading lives with the reports (narratives.py); the names stay here for this page and its tests
from app.narratives import NOT_STORIES, WITHHELD, latest_report, withheld  # noqa: E402, F401

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
# Fewer tellers than this aren't shown: at five to nine people (half of what the finder keeps) most groups are a
# handful reacting to the same news, not a story people retell. The floor grows with the sample, 1 in PEOPLE_SHARE.
MIN_PEOPLE = 10
PEOPLE_SHARE = 2500
SIDE_INK = {'left': '#1a5cff', 'right': '#e0102e', 'both': '#7a3fd1', 'none': '#8a8f98'}


FOCUS_EPISODES = 4  # Focus Group episodes shown, the latest
CHECK_DAYS = 30  # fact-checks this recent
# Where a card's claim was heard: the source chips on each card, and folklore.html#checks, #shows, #posts
SOURCES = {'posts': {'emoji': '🧶', 'name': 'retold online', 'about': 'Told by many people in their own words on Bluesky and Mastodon'},
           'shows': {'emoji': '🎙️', 'name': 'on the shows', 'about': 'Told on two or more of the podcasts, call-in and video shows we transcribe'},
           'checks': {'emoji': '🔎', 'name': 'fact-checked', 'about': 'Examined by a fact-checker in the last 30 days'}}
MOVED = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Moved</title>'
         '<link rel="canonical" href="{to}"><meta http-equiv="refresh" content="0; url={to}"></head>'
         '<body><p>Rumors are now part of <a href="{to}">Folklore and rumors</a>.</p></body></html>')
# What's told on the shows reaches the public page only once plain news is filtered out: the first 25 were mostly
# daily news podcasts repeating the news (BBC, Reuters, Up First, Morning Wire), not claims people tell (Oct 8)
SHOWS_PUBLIC = False
# Appeals for money with no politics in them (Oct 27: "A friend's animal charity needs donations", 285 accounts posting
# once each, no replies, nothing shared) are a spam wave's shape, not a story people tell: kept off the public page
APPEAL = re.compile(r'donat|charit|fundrais|gofundme|crowdfund', re.I)


def appeal(label: dict) -> bool:
    """A retold card that only asks for money: a non-political appeal for donations"""
    return not label.get('politics') and bool(APPEAL.search(f"{label.get('narrative', '')} {label.get('motif', '')}"))
SHOW_INK = {'left': '#3a86ff', 'right': '#ff4f6d', 'center': '#b8b8c8'}  # as the front page's shows (page_headlines)


def motif_cards(index: dict, claim: str) -> list[dict]:
    """The motif-index entries a claim is filed under, for its card: id, name and how many claims each holds. Only
    motifs a person has verified, and only if they saw this claim in it (motif_index.public)."""
    k = motif_index.key(claim) if claim else None
    return [{'id': e['id'], 'name': e['name'], 'count': len(motif_index.public_claims(e)), 'note': motif_index.public_note(e),
             'genre': motif_index.person_genre(e)}
            for e in (motif_index.entries_of(index, claim) if claim else [])
            if motif_index.public(e) and not e.get('watch') and k in set(e.get('done') or [])]


def genres(motifs: list[dict]) -> list[str]:
    """A card's genres: those the person gave the motifs it's filed under (a genre belongs to a motif, not a claim)"""
    return sorted({m['genre'] for m in motifs if m.get('genre')}, key=str.lower)


def counted(cards: list[dict], key: str) -> list[tuple[str, int]]:
    """(value, cards with it) for a filter row, most first; `key` a card's single value or its list of values"""
    return Counter(v for c in cards for v in (c[key] if isinstance(c.get(key), list) else [c.get(key)]) if v).most_common()


def checked_cards(index: dict, linked: set[str]) -> list[dict]:
    """A card per fact-check from the last CHECK_DAYS that names a claim, newest first, except those already linked
    from a narrative's card (`linked`, their urls): the claim in the model's words, its shape, and whether people in
    our social sample are telling it (app/analysis/circulation.py)"""
    try:
        items = factchecks._items(CHECK_DAYS)
        labels = factchecks.label_all(items)
    except Exception as e:  # noqa: BLE001 - e.g. no side_item table on a database that hasn't migrated
        logger.warning("Folklore: no fact-checks (%s)", e)
        return []
    looked = circulation.load()
    seen = looked.get('claims', {})
    cards = []
    for item in items:
        label = labels.get(item['url'])
        if not label or not label.get('claim') or item['url'] in linked:
            continue  # not labeled yet, a roundup that checks no single claim, or shown on its narrative's card
        claim = motif_index.corrected(label['claim'], index)  # a person's correction of the summary, if any
        motifs = motif_cards(index, claim)
        cards.append({'kind': 'checks', 'sources': ['checks'], 'claim': claim, 'title': item['title'], 'url': item['url'],
                      'checker': item['source'], 'date': item['published'][:10], 'politics': bool(label.get('politics')),
                      'rumor_class': label.get('rumor_class') if label.get('rumor_class') != 'other' else None,
                      'conspiracy': (label.get('conspiracy') if label.get('conspiracy') != 'not a conspiracy' else None),
                      'family': label.get('family') if label.get('family') != 'none' else None,
                      'seen': seen.get(item['url']) if looked else None, 'looked_hours': looked.get('hours') if looked else None,
                      'motifs': motifs, 'genres': genres(motifs)})
    return cards


def show_cards(index: dict, screen) -> list[dict]:
    """A card per claim told on two or more shows (or by two callers), as the hourly run last grouped them
    (show_claims.kept_retold): the claim in our words, which shows told it, and how many callers; never the quotes
    or who the callers were"""
    cards = []
    for r in show_claims.kept_retold():
        told = motif_index.corrected(r['claim'], index)
        shown = screen.shown(told, show_claims.SOURCE)
        if not shown:
            continue
        leans = {s['show']: s.get('lean') for s in r.get('told', [])}
        motifs = motif_cards(index, told)
        cards.append({'kind': 'shows', 'sources': ['shows'], 'claim': shown, 'date': r['date'], 'politics': True,
                      'shows': [{'name': s, 'ink': SHOW_INK.get(leans.get(s) or '', '#b8b8c8')} for s in r['shows']],
                      'tellings': r['tellings'], 'callers': (r.get('speakers') or {}).get('caller', 0),
                      'leans': {k: n for k, n in (r.get('leans') or {}).items() if k},
                      'rumor_class': None, 'conspiracy': None, 'family': None, 'motifs': motifs, 'genres': genres(motifs)})
    return cards


def told_before(threads: dict, report: str, claim: str, index: dict) -> list[dict]:
    """The earlier days the same narrative was told (app/analysis/narrative_threads.py), newest first, in our words"""
    thread = narrative_threads.thread_of(threads, report, claim)
    if not thread:
        return []
    return [{'day': date.fromisoformat(d['date']).strftime('%b %-d'), 'people': d['people'],
             'claim': motif_index.corrected(d['claim'], index)}
            for d in reversed(thread['days']) if d['report'] != report]


# The motif lists at the top of the page, as ranked strips in pairs that answer each other (Oct 28: they were chip walls
# with "×56 🫏6 · 15🐘"): told a lot and never checked | the fact-checkers' favorites; told most lately | gone quiet;
# only voters say | only the shows say. Colored by genre; a two-tone bar where left or right shows said it
BOARD_TOP = 10
QUIET_DAYS, QUIET_BEFORE, QUIET_LEAST = 7, 14, 5  # gone quiet: 5+ claims in the 14 days before the last 7, at most 1 since
ONLY_SHOWS_LEAST = 3  # only the shows say: told on at least this many shows


def motif_stats(rows: list[dict]) -> dict[str, dict]:
    """motif -> who told it: {kinds (shows, posts, check, voters), shows (every show that told it), left, right (the
    shows whose own host or guest said it, as the aisle counts sides)}"""
    from app.analysis import motif_web
    by = defaultdict(list)
    for r in rows:
        by[r['motif']].append(r)
    out = {}
    for m, rs in by.items():
        said = motif_web.sided(motif_web.spoken(rs))
        out[m] = {'kinds': {r['kind'] for r in rs}, 'shows': sorted({r['teller'] for r in rs if r['kind'] == 'shows'}),
                  'left': len(said['left']), 'right': len(said['right'])}
    return out


def split_of(stat: dict | None) -> float | None:
    """The left share of the shows on either side that said it, for a two-tone bar; None when neither side did"""
    if not stat or not (stat['left'] + stat['right']):
        return None
    return stat['left'] / (stat['left'] + stat['right'])


def sides_line(stat: dict | None) -> str:
    if not stat or not (stat['left'] + stat['right']):
        return ''
    return f"🫏 said on {stat['left']} left and {stat['right']} right shows 🐘 (by a host or guest)"


def gone_quiet(entries: list[dict], today: date | None = None) -> list[dict]:
    """The motifs told a lot before and little lately: QUIET_LEAST or more claims dated in the QUIET_BEFORE days before
    the last QUIET_DAYS, and at most one in those last days. [{entry, before, since}], the most told before first"""
    today = today or date.today()
    cut = (today - timedelta(days=QUIET_DAYS)).isoformat()
    start = (today - timedelta(days=QUIET_DAYS + QUIET_BEFORE)).isoformat()
    out = []
    for e in entries:
        dates = [str(c.get('date', ''))[:10] for c in e['claims']]
        before = sum(start < d <= cut for d in dates)
        since = sum(d > cut for d in dates)
        if before >= QUIET_LEAST and since <= 1:
            out.append({'entry': e, 'before': before, 'since': since})
    return sorted(out, key=lambda q: (-q['before'], q['since'], q['entry']['name'].lower()))


def only_shows(entries: dict[str, dict], stats: dict[str, dict]) -> list[dict]:
    """The motifs only the shows told: on ONLY_SHOWS_LEAST or more shows, and never by people online, a fact-checker
    or the voters. [{entry, stat}], the most shows first"""
    out = [{'entry': entries[m], 'stat': st} for m, st in stats.items()
           if m in entries and st['kinds'] == {'shows'} and len(st['shows']) >= ONLY_SHOWS_LEAST]
    return sorted(out, key=lambda o: (-len(o['stat']['shows']), -o['entry']['count'], o['entry']['name'].lower()))


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def motif_boards(shelf: dict, checking: dict, voters_only: list[dict], rows: list[dict]) -> list[dict]:
    """The six lists, in their pairs, as boards (app/site/boards.py); each row's hover card has its genre, note and
    who told it"""
    entries = {e['id']: e for e in shelf['entries']}
    stats = motif_stats(rows)
    stat = lambda i: stats.get(i['id'])  # noqa: E731

    def strip(items, value, figure, lines, split=True):
        items = [i for i in items if i['id'] in entries][:BOARD_TOP]
        top = max((value(i) for i in items), default=0) or 1
        out = []
        for i in items:
            e = entries[i['id']]
            # "Name: lines" reads in the hover card as a heading and its lines (index.js tipCard)
            tip = '\n'.join(t for t in [f"{GENRE_EMOJI.get(e['genre'], '🧩')} {e['genre'] or 'no genre yet'}",
                                        e.get('note', '')] + lines(i) + [sides_line(stat(i))] if t)
            r = strips.genre_row(e['name'], motif_href(e['id']), e['genre'] or None, value(i), top, figure(i),
                                 tip=f"{e['name']}: {tip}")
            if split and (s := split_of(stat(i))) is not None:
                r['split'] = round(100 * s)
            out.append(r)
        return out

    lately = [{'id': e['id'], 'recent': e['recent'], 'count': e['count']} for e in shelf.get('lately', [])]
    quiet = [{'id': q['entry']['id'], 'before': q['before'], 'since': q['since']} for q in gone_quiet(shelf['entries'])]
    shows_only = [{'id': o['entry']['id'], 'shows': o['stat']['shows']} for o in only_shows(entries, stats)]
    days = shelf.get('lately_days', 3)
    b = strips.board
    return [
        b('unchecked', '🙈', 'Told a lot, never checked', '#ff6b1a', 'the most different claims told on the shows and '
          'online that no fact-checker we follow has examined; the bar is how many. A list of leads, not of '
          'falsehoods: many are opinions, or true',
          strip(checking.get('unchecked', []), lambda i: i['told'], lambda i: plural(i['told'], 'claim'),
                lambda i: [f"{plural(i['told'], 'different claim')} told, {i['posts']} of them online",
                           '🔎 no fact-check yet']),
          empty='🦗 Every much-told motif has been checked at least once.'),
        b('checked', '🔎', "The fact-checkers' favorites", '#ffc400', 'the motifs fact-checkers examined most; the bar '
          'is how many of its claims they checked',
          strip(checking.get('checked', []), lambda i: i['checked'], lambda i: f"🔎 {i['checked']}",
                lambda i: [f"🔎 {plural(i['checked'], 'claim')} checked, {i['told']} told on the shows and online"]),
          empty='🦗 No fact-check is filed under a motif yet.'),
        b('lately', '🔥', 'Told most lately', '#ff4fa3', f'the most claims dated in the last {days} days; the bar is '
          'how many',
          strip(lately, lambda i: i['recent'], lambda i: f"{i['recent']} lately",
                lambda i: [f"🔥 {i['recent']} of its {plural(i['count'], 'claim')} in the last {days} days"]),
          empty='🦗 Nothing filed in the last few days.'),
        b('quiet', '🧊', 'Gone quiet', '#8a8f98', f'told {QUIET_LEAST} or more times in the {QUIET_BEFORE} days before '
          f'last week, and once at most in the {QUIET_DAYS} days since; the bar is the claims before',
          strip(quiet, lambda i: i['before'], lambda i: f"{i['before']} → {i['since']}",
                lambda i: [f"🧊 {plural(i['before'], 'claim')} in the {QUIET_BEFORE} days before last week, "
                           f"{i['since']} in the last {QUIET_DAYS}"]),
          empty='🦗 Nothing much-told has gone quiet.'),
        b('voters', '🗳️', 'Only voters say', '#8a5cff', "told by the voters in The Focus Group (below) and by no show, "
          "poster or fact-checker we follow; the bar is its claims. Many are praise for a candidate",
          strip(voters_only, lambda i: i['claims'], lambda i: plural(i['claims'], 'claim'),
                lambda i: [f"🗳️ {plural(i['claims'], 'claim')} from voters, nowhere else"], split=False),
          empty='🦗 Nothing the voters say is theirs alone.'),
        b('shows', '🎙️', 'Only the shows say', '#00c2a8', f'told on {ONLY_SHOWS_LEAST} or more of the shows we follow '
          'and never by people online, a fact-checker or the voters; the bar is how many shows',
          strip(shows_only, lambda i: len(i['shows']), lambda i: plural(len(i['shows']), 'show'),
                lambda i: [f"🎙️ told on {plural(len(i['shows']), 'show')}: {', '.join(i['shows'][:8])}"
                           + (f" and {len(i['shows']) - 8} more" if len(i['shows']) > 8 else '')]),
          empty='🦗 Everything the shows tell is told elsewhere too.'),
    ]


class FolklorePage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('folklore.html')

    def generate(self):
        logger.info("Generating folklore page...")
        report = latest_report()
        cards, copies, fewer = [], [], 0
        bsky = bluesky_examples.prepared()
        pulled = withheld()
        index = motif_index.load()
        threads = narrative_threads.load()
        screen = accusations.screen()  # claims accusing a named private person of a crime: name swapped out, or held
        floor = max(MIN_PEOPLE, round(report['authors'] / PEOPLE_SHARE)) if report else MIN_PEOPLE
        if report:
            for g in report['found']:
                label = g.get('label') or {}
                if label.get('narrative') in pulled or (label.get('retold') and appeal(label)):
                    continue
                if label.get('retold') and g['authors'] < floor:
                    fewer += 1
                elif label.get('retold'):
                    claim = motif_index.corrected(label.get('narrative') or '', index)
                    shown = screen.shown(claim)
                    if not shown:
                        continue
                    named = shown == claim  # else its cast, posts and earlier tellings may name the person too
                    motifs = motif_cards(index, claim)
                    cards.append({
                        'kind': 'posts', 'sources': ['posts'] + (['checks'] if g.get('factchecks') else []),
                        'claim': shown, 'people': g['authors'], 'posts': g['posts'],
                        'variety': g['variety'], 'variety_pct': round(100 * g['variety']),
                        'politics': bool(label.get('politics')),
                        # Shown on the site only from evidence (the lean of the outlets its posts share); the
                        # model's guess, unchecked, only in previews
                        'side': g.get('shared_side') or (label.get('side', 'none') if Config.debug else None),
                        'side_from': 'shares' if g.get('shared_side') else 'model',
                        'side_ink': SIDE_INK.get(g.get('shared_side') or label.get('side'), '#8a8f98'),
                        'story_shape': label.get('genre') not in NOT_STORIES,
                        'rumor_class': label.get('rumor_class') if label.get('rumor_class') != 'other' else None,
                        'conspiracy': label.get('conspiracy') if label.get('conspiracy') != 'not a conspiracy' else None,
                        'family': label.get('family') if label.get('family') != 'none' else None,
                        'story': g.get('story'), 'articles': g.get('articles') or [],
                        'factchecks': g.get('factchecks') or [],
                        'motifs': motifs, 'genres': genres(motifs),
                        'examples': g['examples'][:4] if Config.debug and named else [],
                        'bluesky': bluesky_examples.examples(g.get('uris'), bsky) if named else [],
                        'told_before': [{**b, 'claim': c} for b in told_before(threads, report.get('file', ''), label.get('narrative') or '', index)
                                        if (c := screen.shown(b['claim']))],
                    })
                elif g['kind'] == 'copypasta':
                    copies.append({'people': g['authors'], 'posts': g['posts'],
                                   'example': g['examples'][0] if Config.debug else None})
        # What voters say in The Focus Group's episodes, the latest few, in our words (never their quotes), with the
        # motifs each claim is filed under: a source of its own beside the posts
        from app.analysis import focus_group
        voters = []
        for url, ep in sorted(focus_group.load().items(), key=lambda kv: kv[1].get('date', ''), reverse=True)[:FOCUS_EPISODES]:
            said = [{'claim': shown, 'side': c.get('side') or '', 'motifs': motif_cards(index, told)}
                    for c in ep.get('claims', []) if (told := motif_index.corrected(c['claim'], index))
                    and (shown := screen.shown(told, 'Focus Group'))]
            if said:
                voters.append({'title': ep['title'], 'date': ep['date'], 'url': url, 'claims': said})
        # Then what's told on the shows, and the fact-checks no narrative's card links already
        if SHOWS_PUBLIC or Config.debug:
            cards += show_cards(index, screen)
        cards += checked_cards(index, {p['url'] for c in cards for p in c.get('factchecks', [])})
        shelf = catalog(index, screen)  # the motif index itself, which the page opens on
        try:  # told against checked, and what only voters tell, by motif (motif_web)
            from app.analysis import motif_web
            from app.site.page_motif import shared
            told_rows = shared()['web']['rows']
            checking, voters_only = motif_web.checked_vs_told(told_rows), motif_web.voters_only(told_rows)
        except Exception as e:  # noqa: BLE001 - extra
            logger.warning("Folklore: checked against told: %s", e)
            checking, voters_only, told_rows = {}, [], []
        boards = motif_boards(shelf, checking, voters_only, told_rows) if shelf['entries'] else []
        screen.save()
        looked = circulation.load()
        self.template.write({
            'title': 'Folklore and rumors', 'bsky_rule': bluesky_examples.RULE, 'bsky_script': bluesky_examples.SCRIPT,
            'boards': boards, 'genre_key': strips.genre_key([r for b in boards for r in b['rows']]),
            'genre_inks': strips.GENRE_INK,
            'report': report, 'cards': cards, 'copies': copies, 'voters': voters, 'floor': floor, 'fewer': fewer,
            'sources': SOURCES, 'kinds': Counter(c['kind'] for c in cards), 'genre_counts': counted(cards, 'genres'),
            'rumor_classes': RUMOR_CLASSES, 'conspiracy_scopes': CONSPIRACY_SCOPES, 'shape_emoji': SHAPE_EMOJI,
            'index': shelf, 'looked': looked,
            'check_days': CHECK_DAYS, 'checkers': sorted({c['checker'] for c in cards if c['kind'] == 'checks'}),
            'preview': Config.debug, 'shows_on': SHOWS_PUBLIC or Config.debug,
        })
        # The Rumors page was folded in here (Oct 8): its address opens this one on the fact-checks
        with open(os.path.join(Config.build, 'rumors.html'), 'w', encoding='utf-8') as f:
            f.write(MOVED.format(to='folklore.html#checks'))
        logger.info("...%d cards (%s), %d copypasta groups", len(cards),
                    ', '.join(f'{n} {k}' for k, n in Counter(c['kind'] for c in cards).items()), len(copies))
