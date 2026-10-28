"""A page for each show we transcribe (Oct 27): what it tells, as the motif index files its claims. Its signature (the
motifs it tells far more often than the other shows: picked by weighted log-odds, motif_web.shows, shown by how many
times more often) beside the motifs the other shows tell that it never does; its repertoire (the motifs its claims came
up in); the shows that tell the most and the least alike (by their motifs, not by their lean); and its latest claims.

Oct 28 (the site redo): the three lists were walls of motif and show chips. They're ranked strips now (boards.py), in
pairs that answer each other, the motifs colored by genre and the shows by their lean, the detail in hover cards."""
import math
import os
from collections import Counter, defaultdict

from app.analysis import motif_web
from app.site import boards
from app.site.common import TemplateHandler, motif_href
from app.site.page_motif import LEAN_INK, shared
from app.site.page_motifs import GENRE_EMOJI
from app.utils import get_logger
from app.utils.config import Config

logger = get_logger(__name__)

LATEST = 30  # claims listed, newest first
REPERTOIRE, FIRST = 40, 20  # motifs listed in its repertoire, the first FIRST in one board and the rest beside it
NEVER = 10  # motifs the others tell that it doesn't
ALIKE = 6  # shows in each of Most alike and Least alike
MORE_LEAST = 1.5  # a signature motif shown in "Tells more than others" at this many times the others' rate or more
SHARED = 3  # motifs named in an alike row's card
LEAN_WORDS = {'left': 'leans left', 'right': 'leans right', 'center': 'center', 'crossover': 'crossover',
              'unrated': 'not grouped by lean'}


def show_href(show: str) -> str:
    return f'show-{motif_web.show_slug(show)}.html'


def tellings(rows: list[dict]) -> dict:
    """What the boards count, from the motif web's rows: {counts: show -> Counter(motif), genre, name: motif -> ...,
    tellers: motif -> shows that told it}"""
    counts, genre, name, tellers = defaultdict(Counter), {}, {}, defaultdict(set)
    for r in rows:
        if r['kind'] != 'shows':
            continue
        counts[r['teller']][r['motif']] += 1
        genre.setdefault(r['motif'], r.get('genre'))
        name[r['motif']] = r['name']
        tellers[r['motif']].add(r['teller'])
    return {'counts': counts, 'genre': genre, 'name': name, 'tellers': tellers}


def times_more(y_s: int, n_s: int, y_o: int, n_o: int) -> float:
    """How many times more often a show tells a motif than the other shows do: its share of its own tellings over
    theirs, one telling added to theirs so a motif they never told doesn't divide by nothing"""
    return (y_s / (n_s or 1)) / ((y_o + 1) / (n_o or 1))


def times(x: float) -> str:
    return f'×{x:.0f}' if x >= 10 else f'×{x:.1f}'


def tells_more(show: str, sh: dict, t: dict) -> list[dict]:
    """Its signature motifs it tells at least MORE_LEAST times as often as the others, the most times first: a row
    each, colored by genre, the bar how many times more often"""
    counts = t['counts']
    n_s = sum(counts[show].values())
    n_o = sum(sum(c.values()) for s, c in counts.items() if s != show)
    items = []
    for m, name, _ in sh['signature']:
        y_s = counts[show][m]
        y_o = sum(c[m] for s, c in counts.items() if s != show)
        x = times_more(y_s, n_s, y_o, n_o)
        if x >= MORE_LEAST:
            items.append((m, name, y_s, y_o, x))
    items.sort(key=lambda i: -i[4])
    top = max((i[4] for i in items), default=1)
    others = len(counts) - 1
    rows = []
    for m, name, y_s, y_o, x in items:
        g = t['genre'].get(m)
        theirs = (f'the other {others} shows: {y_o} of their {n_o:,} ({y_o / (n_o or 1):.2%})' if y_o
                  else f'none of the other {others} shows told it')
        tip = (f"{g or 'No genre yet'}\n{show}: {y_s} of its {n_s:,} tellings ({y_s / (n_s or 1):.1%})\n{theirs}\n"
               f"{times(x)} as often{' (if they had told it once)' if not y_o else ''}")
        rows.append(boards.genre_row(name, motif_href(m), g, x, top, 'only here' if not y_o else times(x), tip=tip))
    return rows


def never_tells(show: str, t: dict, lean: dict) -> list[dict]:
    """The motifs told on the most other shows that this one never told: a row each, colored by genre, the bar how
    many other shows told it"""
    mine = t['counts'][show]
    items = sorted(((m, sorted(s for s in ss if s != show)) for m, ss in t['tellers'].items() if m not in mine),
                   key=lambda i: (-len(i[1]), -sum(t['counts'][s][i[0]] for s in i[1]), t['name'][i[0]]))[:NEVER]
    top = max((len(s) for _, s in items), default=1)
    rows = []
    for m, shows in items:
        g = t['genre'].get(m)
        sides = Counter(lean.get(s) or 'unrated' for s in shows)
        mix = ' · '.join(f"{boards.LEAN_EMOJI[k]} {sides[k]} {LEAN_WORDS[k]}" for k in ('left', 'center', 'right',
                                                                                         'crossover', 'unrated')
                         if sides[k])
        tip = (f"{g or 'No genre yet'}\nTold on {len(shows)} other shows, "
               f"{sum(t['counts'][s][m] for s in shows)} times; never on {show}\n{mix}")
        rows.append(boards.genre_row(t['name'][m], motif_href(m), g, len(shows), top, f'{len(shows)} shows', tip=tip))
    return rows


def repertoire(show: str, sh: dict, t: dict) -> list[dict]:
    """Its most told motifs, REPERTOIRE of them: a row each, colored by genre, the bar how many of its claims"""
    items = sh['motifs'][:REPERTOIRE]
    top = max((n for _, _, n in items), default=1)
    rows = []
    for m, name, n in items:
        g = t['genre'].get(m)
        k = len(t['tellers'][m])
        tip = (f"{g or 'No genre yet'}\nCame up in {n} of its claims\n"
               + (f'Told on {k - 1} other show{"" if k == 2 else "s"} too' if k > 1 else 'Told on no other show'))
        rows.append(boards.genre_row(name, motif_href(m), g, n, top, f'×{n}', tip=tip))
    return rows


def genre_mix(show: str, t: dict) -> list[dict]:
    """Its tellings by genre, the biggest first: [{genre, mark, ink, n, share}]"""
    by = Counter()
    for m, n in t['counts'][show].items():
        by[t['genre'].get(m) or 'No genre yet'] += n
    total = sum(by.values()) or 1
    return [{'genre': g, 'mark': GENRE_EMOJI.get(g, '🧩'), 'ink': boards.GENRE_INK.get(g, boards.UNCOLORED), 'n': n,
             'share': round(100 * n / total, 1)} for g, n in by.most_common()]


def likeness(t: dict, kept: list[str]) -> dict[str, dict[str, float]]:
    """How alike each pair of shows tell: the cosine of their tellings by motif (1: the same motifs in the same
    proportions, 0: none in common), as motif_web.shows works out its neighbours"""
    norm = {s: math.sqrt(sum(n * n for n in t['counts'][s].values())) or 1 for s in kept}
    out = defaultdict(dict)
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            ca, cb = t['counts'][a], t['counts'][b]
            small, big = (ca, cb) if len(ca) < len(cb) else (cb, ca)
            x = sum(n * big[m] for m, n in small.items()) / (norm[a] * norm[b])
            out[a][b] = out[b][a] = x
    return out


def alike_rows(show: str, others: list[tuple[str, float]], t: dict, lean: dict, pages: set) -> list[dict]:
    """Other shows, a row each, colored by their lean, the bar how alike their motifs are"""
    rows = []
    for o, x in others:
        side = lean.get(o) or 'unrated'
        shared = sorted((m for m in t['counts'][show] if m in t['counts'][o]),
                        key=lambda m: (-min(t['counts'][show][m], t['counts'][o][m]), t['name'][m]))
        tip = (f"{LEAN_WORDS[side].capitalize()} · {x:.0%} alike\n"
               f"{len(shared)} motifs in common" + (': ' + ', '.join(t['name'][m] for m in shared[:SHARED])
                                                     + ('…' if len(shared) > SHARED else '') if shared else ''))
        rows.append(boards.row(o, show_href(o) if o in pages else None, x, 1, f'{x:.0%}', tip=tip,
                               ink=boards.LEAN_INK[side], mark=boards.LEAN_EMOJI[side], mark_label=LEAN_WORDS[side]))
    return rows


def lean_key(leans) -> list[dict]:
    return [{'name': LEAN_WORDS[k], 'mark': boards.LEAN_EMOJI[k], 'ink': boards.LEAN_INK[k]}
            for k in ('left', 'center', 'crossover', 'right', 'unrated') if k in leans]


def show_boards(show: str, sh: dict, t: dict, lean: dict, likes: dict) -> dict:
    """The page's boards: signature (more | never), repertoire (two halves), alike (most | least)"""
    more = boards.board('more', '✍️', 'Tells more than others', '#ff4fa3',
                        'motifs it tells far more often than the other shows we follow; the bar is how many times '
                        'more often, by its share of its tellings against theirs', tells_more(show, sh, t),
                        empty='🦗 Nothing it tells stands out from the other shows yet.')
    never = boards.board('never', '🙈', "Others tell, it doesn't", '#8a8f98',
                         'motifs told on the most other shows that never came up on this one; the bar is how many '
                         'other shows told it', never_tells(show, t, lean))
    rep = repertoire(show, sh, t)
    half = FIRST  # the second board counts on from FIRST (762-redo-b.css)
    reps = [boards.board('rep-top', '🧩', 'Told most', '#8a5cff',
                         'the motifs its claims came up in, the most first; the bar is how many of its claims',
                         rep[:half])]
    if rep[half:]:
        reps.append(boards.board('rep-next', '🧩', 'And then', '#b9a3ff', 'the bar on the same scale as the first',
                                 rep[half:]))
    near = sorted(likes.get(show, {}).items(), key=lambda i: (-i[1], i[0]))
    pages = set(likes)
    alike = [boards.board('alike', '👯', 'Most alike', '#00c2a8',
                          'the shows whose motifs overlap most with its own, whatever their lean; the bar is how alike '
                          '(100%: the same motifs in the same proportions)',
                          alike_rows(show, near[:ALIKE], t, lean, pages)),
             boards.board('unalike', '🙃', 'Least alike', '#ffc400',
                          'the shows with the least in common with it; the bar is how alike, on the same scale',
                          alike_rows(show, near[ALIKE:][::-1][:ALIKE], t, lean, pages),  # never one of the most alike
                          empty='🦗 Too few shows to say.')]
    return {'signature': [more, never], 'repertoire': reps, 'alike': alike,
            'genre_key': boards.genre_key([r for b in [more, never] + reps for r in b['rows']]),
            'lean_key': lean_key({lean.get(o) or 'unrated' for o, _ in near}), 'mix': genre_mix(show, t),
            'repertoire_shown': REPERTOIRE}


class ShowPages:
    def __init__(self, dh=None):
        self.template = TemplateHandler('show.html')

    def generate(self):
        logger.info("Generating show pages...")
        web = shared()['web']
        shows = web['shows']
        t = tellings(web['rows'])
        lean = {o: shows[o]['lean'] for o in shows}
        likes = likeness(t, sorted(shows))
        for name, sh in shows.items():
            mine = sorted((r for r in web['rows'] if r['kind'] == 'shows' and r['teller'] == name),
                          key=lambda r: r['date'], reverse=True)
            latest, seen = [], set()
            for r in mine:
                if r['key'] in seen:
                    for c in latest:
                        if c['key'] == r['key'] and r['motif'] not in [m[0] for m in c['motifs']]:
                            c['motifs'].append((r['motif'], r['name']))
                    continue
                seen.add(r['key'])
                if len(latest) < LATEST:
                    latest.append({'key': r['key'], 'claim': r['claim'], 'date': r['date'], 'url': r['url'],
                                   'motifs': [(r['motif'], r['name'])]})
            self.template.write({
                'title': name, 'og_title': f'What {name} tells · bignews.day',
                'og_description': f"The stories {name} tells, from our motif index: "
                                  + ', '.join(n for _, n, _ in sh['signature'][:5]) + '.',
                'sh': sh, 'ink': LEAN_INK.get(sh['lean'] or '', '#b8b8c8'), 'latest': latest,
                **show_boards(name, sh, t, lean, likes),
            }, os.path.join(Config.build, show_href(name)))
        logger.info("...%d show pages", len(shows))
