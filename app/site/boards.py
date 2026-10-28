"""Ranked strips, the site's way of showing a list (Oct 28). The aisle's lists were walls of identical chips, "plain as
hell" (the person); as ranked strips in pairs that answer each other, colored by an axis the list doesn't already
show, they loved them, and asked for the same everywhere ("Use that as an example ... do it all").

A board is one list: a banner, a line saying what its bar measures, and its rows. A row is a rank, a colored disc with
an emoji (the colored axis: genre, lean, outlet type...; the emoji goes with the color, never color alone), the name,
a thin bar for the list's measure, and the figure; its detail goes in data-tip, for the hover cards (index.js). Boards
sit two by two, so a pair (Rising | Fading) reads side by side, one under the other on a phone. A key names the colors.

    rows = [row(o['name'], o['href'], o['anger'], top, f"{o['anger']:.0%}", tip=..., ink=LEAN_INK[o['side']],
                mark='🫏', mark_label='leans left') for o in angriest]
    boards = [board('angry', '🤬', 'Angriest', '#e8463c', 'the bar is the share of its headlines read as anger', rows),
              ...]

The template side is templates/boards.html (`{% import 'boards.html' as b %}{{ b.boards(boards) }}`, `b.key(...)`),
the styles styles/175-boards.css. Templates don't escape on their own here: the macros escape every field."""

# Lean colors, the site's own (the aisle map, the lean bars)
LEAN_INK = {'left': '#3a86ff', 'lean left': '#8fb8ff', 'center': '#b8b8c8', 'lean right': '#ff9aa8', 'right': '#ff4f6d',
            'crossover': '#8a5cff', 'unrated': '#ffffff'}
LEAN_EMOJI = {'left': '🫏', 'lean left': '🫏', 'center': '⚖️', 'lean right': '🐘', 'right': '🐘', 'crossover': '🔀',
              'unrated': '⚪'}

# Motif genres (page_motifs.GENRE_EMOJI): five colors for the five biggest (93% of tellings). Of 14 hues tried, no set
# of more than five stays apart for every pair under color blindness (the dataviz validator, all pairs on white: worst
# deutan ΔE 7.6, the olive and brown, in the floor band, so the emoji always goes with the color), and none is the lean
# blue or red. The rest stay white, known by their emoji. Fixed to the genre, in GENRE_EMOJI order, never cycled.
GENRE_INK = {'Archetypes': '#e87ba4', 'Plots': '#a0522d', 'Beliefs': '#7a8a00', 'Theories': '#8a5cff',
             'Arguments': '#eda100'}
UNCOLORED = '#ffffff'
GENRE_SHORT = {'Archetypes': 'a kind of person', 'Plots': 'what happened', 'Beliefs': 'a premise',
               'Theories': 'what people think is behind it', 'Arguments': 'a move in an argument',
               'Values': 'how things ought to be', 'Exhortations': 'a call to act', 'Perennials': 'safe small talk'}


def bar(value, top, least: int = 4) -> int:
    """A bar's length in percent of the board's biggest, at least `least` so a small one still shows"""
    return max(least, round(100 * (value or 0) / (top or 1))) if top else least


def row(name: str, href: str | None, value, top, figure: str, tip: str = '', ink: str = UNCOLORED, mark: str = '•',
        mark_label: str = '', split: float | None = None) -> dict:
    """One row of a board. `split` (0-1) draws the bar in two tones, the left share in blue and the rest in red (a
    left/right mix); otherwise the bar is in the row's ink"""
    return {'name': name, 'href': href, 'bar': bar(value, top), 'figure': figure, 'tip': tip, 'ink': ink,
            'mark': mark, 'mark_label': mark_label, 'split': None if split is None else round(100 * split)}


def board(key: str, emoji: str, title: str, stage: str, sub: str, rows: list[dict],
          empty: str = '🦗 Nothing fits this list today.') -> dict:
    """One list: its banner (emoji, title, the banner's color), what its bar measures, its rows"""
    return {'key': key, 'emoji': emoji, 'title': title, 'stage': stage, 'sub': sub, 'rows': rows, 'empty': empty}


def genre_key(rows: list[dict] | None = None) -> list[dict]:
    """The genre colors' key: the colored genres, then the white ones the rows hold (all of them without rows)"""
    from app.site.page_motifs import GENRE_EMOJI
    shown = {r.get('genre') for r in rows} if rows is not None else set(GENRE_EMOJI)
    key = [{'name': g, 'mark': GENRE_EMOJI[g], 'ink': ink, 'about': GENRE_SHORT.get(g, '')}
           for g, ink in GENRE_INK.items()]
    rest = [g for g in GENRE_EMOJI if g not in GENRE_INK and g in shown]
    return key + [{'name': g, 'mark': GENRE_EMOJI[g], 'ink': UNCOLORED, 'about': GENRE_SHORT.get(g, ''),
                   'note': '⚪ left white, the smaller genres:' if i == 0 else ''} for i, g in enumerate(rest)]


def genre_row(name: str, href: str | None, genre: str | None, value, top, figure: str, tip: str = '') -> dict:
    """A row colored by its motif's genre"""
    from app.site.page_motifs import GENRE_EMOJI
    r = row(name, href, value, top, figure, tip=tip, ink=GENRE_INK.get(genre, UNCOLORED),
            mark=GENRE_EMOJI.get(genre, '🧩'), mark_label=genre or 'No genre yet')
    r['genre'] = genre or 'No genre yet'
    return r
