"""The Stream Deck Mini as a window on the news (Oct 11; the person picked this over a review pad, "i like idea 2 a lot
more"). Six keys, each a little screen, redrawn every second from what's looked up every LOOK seconds:

    📰 news day     🧬 newborn motif   🔝 most retold
    🌡 mood ring    🎛 the GPU          🦄 unicorn

📰 the last hourly build's news-day meter (big, normal or slow; app/site/page_headlines.py saves it) and the top
   story's share of front pages; it flashes on a big news day. Press: the top story on bignews.day.
🧬 motifs born today: how many, and the newest's name; it glows while there's one you haven't met here. Press: a
   desktop card with its name, note and first claims, and a button to open the checker, where it's renamed or approved.
🔝 the motifs most retold today, one at a time. Press: its card.
🌡 the strongest emotion in the headlines on front pages now, in its colour. Press: every emotion's share.
🎛 who has the GPU and how hard it works, in the lights' colours (app/lights.py). Press: the desktop panel's text.
🦄 Press: the card's own rainbow for PARTY_SECONDS (the "unicorn puke" the lights otherwise keep off), then back to
   work colours.

At night (the lights' NIGHT to DAY) the keys dim. It runs as a user service (deploy/systemd/user/maudlin-deck.service),
exits when the hourly run pulls new code so systemd starts it on that, and waits for the deck when it's unplugged.

Run: python -m app.deck"""
import colorsys
import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime as dt
from html import escape

from app.utils import Config, get_logger

logger = get_logger(__name__)

LOOK = 20  # seconds between lookups
PARTY_SECONDS = 30
CHECKER = 'http://localhost:8766/motif-workbench'
SITE = 'https://bignews.day/'
SEEN = 'deck_seen.json'  # the newborn motifs met on the deck
BRIGHT, DIM = 70, 12  # percent, day and night
EMOJI_FONT = '/usr/share/fonts/noto/NotoColorEmoji.ttf'  # a bitmap font: drawn at its one size, then scaled
TEXT_FONT = '/usr/share/fonts/comic-neue/ComicNeue-Bold.ttf'  # the site's accent face (docs/style-book.md)
NEWS_DAY = {'big': ('🚨', (220, 30, 40)), 'normal': ('📰', (238, 232, 214)), 'slow': ('🌴', (0, 150, 140))}
MOODS = {'fear': ('😨', (140, 60, 255)), 'anger': ('😠', (225, 35, 35)), 'surprise': ('😮', (255, 196, 0)),
         'hope': ('🌱', (50, 190, 90)), 'sadness': ('😢', (45, 105, 225)), 'joy': ('😄', (255, 165, 20)),
         'disgust': ('🤢', (125, 150, 35))}
GPU_TINTS = {'worker': (0, 190, 170), 'experiment': (140, 60, 255), 'hourly': (255, 140, 0), 'idle': (40, 80, 200)}


# What the keys show

def news_day() -> dict | None:
    from app.site.page_headlines import NEWS_DAY_FILE
    from app.utils.store import read_json
    return read_json(NEWS_DAY_FILE, None)


def newborn(index: dict, today: str) -> list[dict]:
    """Motifs born today, newest first"""
    from app.analysis import motif_index as mi
    born = [e for e in mi.live(index) if e.get('first_seen') == today]
    return sorted(born, key=lambda e: int(e['id'][1:]) if e['id'][1:].isdigit() else 0, reverse=True)


def retold(index: dict, today: str, n: int = 3) -> list[tuple[dict, int]]:
    """The n motifs with the most claims dated today, and how many"""
    from app.analysis import motif_index as mi
    counts = [(e, sum(1 for c in e.get('claims', []) if (c.get('date') or '').startswith(today))) for e in mi.live(index)]
    return [(e, k) for e, k in sorted(counts, key=lambda x: -x[1]) if k][:n]


def mood() -> list[tuple[str, float]]:
    """Each emotion's share of the front pages' headlines now (the last scrape's hour), neutral left out, biggest first"""
    db = sqlite3.connect(f'file:{os.path.join(Config.data, "data.db")}?mode=ro', uri=True, timeout=10)
    try:
        rows = db.execute("""select emotion, count(*) from headline where emotion is not null and emotion != 'neutral'
                             and last_accessed > datetime((select max(last_accessed) from headline), '-70 minutes')
                             group by emotion""").fetchall()
    finally:
        db.close()
    total = sum(n for _, n in rows) or 1
    return sorted(((e, n / total) for e, n in rows if e in MOODS), key=lambda x: -x[1])


def gpu() -> tuple[str, float]:
    from app import lights
    return lights.who(), lights.card()[0]


def look_up(state: dict):
    """Everything the keys show, into `state`; a part that fails keeps its last value"""
    from app.analysis import motif_index as mi
    today = dt.now().strftime('%Y-%m-%d')
    for name, get in (('news', news_day), ('mood', mood), ('gpu', gpu)):
        try:
            state[name] = get()
        except Exception as e:  # noqa: BLE001
            logger.debug("Deck: %s: %s", name, e)
    try:
        index = mi.load()
        state['born'], state['retold'] = newborn(index, today), retold(index, today)
    except Exception as e:  # noqa: BLE001
        logger.debug("Deck: motifs: %s", e)


# Drawing

_fonts = {}


def font(path: str, size: int):
    from PIL import ImageFont
    if (path, size) not in _fonts:
        _fonts[(path, size)] = ImageFont.truetype(path, size)
    return _fonts[(path, size)]


def emoji(char: str, size: int):
    """An emoji as an RGBA image `size` pixels high"""
    from PIL import Image, ImageDraw
    big = Image.new('RGBA', (160, 160))
    ImageDraw.Draw(big).text((0, 0), char, font=font(EMOJI_FONT, 109), embedded_color=True)
    box = big.getbbox()
    if box:
        big = big.crop(box)
    return big.resize((max(1, round(big.width * size / big.height)), size))


def ink(bg: tuple) -> tuple:
    return (20, 20, 30) if 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2] > 150 else (255, 255, 255)


def wrap(text: str, width: int, f) -> list[str]:
    lines, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if f.getlength(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def key(size: tuple, bg, icon: str, lines: list[str], big: str | None = None):
    """A key: the background (a colour, or an image), the emoji on top, a big figure or up to two lines below"""
    from PIL import Image, ImageDraw
    w, h = size
    img = bg.copy() if isinstance(bg, Image.Image) else Image.new('RGB', size, bg)
    col = ink(img.resize((1, 1)).getpixel((0, 0)))
    pic = emoji(icon, 30)
    img.paste(pic, ((w - pic.width) // 2, 5), pic)
    draw = ImageDraw.Draw(img)
    if big:
        f = font(TEXT_FONT, 20)
        draw.text((w / 2, 50), big, font=f, fill=col, anchor='mm')
        lines = lines[:1]
        y = 68
    else:
        y = 46
    small = font(TEXT_FONT, 13)
    text = [' '.join(lines)] if big else [t for line in lines for t in wrap(line, w - 6, small)]
    for line in text[:2 if not big else 1]:
        if small.getlength(line) > w - 4:
            while line and small.getlength(line + '…') > w - 4:
                line = line[:-1]
            line += '…'
        draw.text((w / 2, y), line, font=small, fill=col, anchor='mm')
        y += 15
    return img


def rainbow(size: tuple, shift: float):
    from PIL import Image
    img = Image.new('RGB', size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            r, g, b = colorsys.hsv_to_rgb(((x + y) / (size[0] + size[1]) + shift) % 1, 0.75, 0.95)
            px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    return img


def dim(colour: tuple, t: float) -> tuple:
    return tuple(int(c * t) for c in colour)


def faces(state: dict, size: tuple, now: float) -> list:
    """The six keys' images, in the deck's order"""
    out = []
    news = state.get('news') or {}
    icon, bg = NEWS_DAY.get(news.get('kind'), ('📰', (60, 60, 70)))
    if news.get('kind') == 'big' and int(now) % 2:
        bg = dim(bg, 0.45)  # a big news day flashes
    out.append(key(size, bg, icon, ['news day'], f"{news['share']}%" if news.get('share') is not None else '?'))

    born = state.get('born') or []
    seen = state.get('seen', set())
    fresh = bool(born) and born[0]['id'] not in seen
    bg = (40, 40, 48)
    if fresh:  # glows while there's one not met
        bg = dim((0, 200, 120), 0.55 + 0.45 * abs((now % 2) - 1))
    out.append(key(size, bg, '🧬', [born[0]['name']] if born else ['none yet'], str(len(born)) if born else None))

    top = state.get('retold') or []
    if top:
        e, n = top[int(now / 6) % len(top)]
        out.append(key(size, (255, 79, 163), '🔝', [e['name']], f'×{n}'))
    else:
        out.append(key(size, (60, 60, 70), '🔝', ['nothing today']))

    moods = state.get('mood') or []
    if moods:
        name, share = moods[0]
        icon, bg = MOODS[name]
        out.append(key(size, bg, icon, [name], f'{share:.0%}'))
    else:
        out.append(key(size, (60, 60, 70), '🌡', ['no mood']))

    who, load = state.get('gpu') or ('idle', 0.0)
    out.append(key(size, dim(GPU_TINTS.get(who, (60, 60, 70)), 0.6 + 0.4 * min(1, load / 100)), '🎛', [who],
                   f'{load:.0f}%'))

    left = state.get('party_until', 0) - now
    out.append(key(size, rainbow(size, now / 4 if left > 0 else 0), '🦄',
                   [f'{left:.0f} s' if left > 0 else 'unicorn']))
    return out


# Pressing

def card(title: str, body: str, url: str | None = None, label: str = 'Open'):
    """A desktop notification; with `url`, a button that opens it. In a thread: notify-send waits for the click"""
    def show():
        cmd = ['notify-send', '-a', 'bignews.day', '-t', '30000', title, body]
        if url:
            cmd[1:1] = ['-A', f'open={label}', '-A', 'later=Later', '--wait']
        try:
            chosen = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout.strip()
            if url and chosen == 'open':
                subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning("Deck: card: %s", e)
    threading.Thread(target=show, daemon=True).start()


def motif_card(e: dict, why: str):
    claims = [c['claim'] for c in e.get('claims', [])][:2]
    body = (f"<i>{escape(e.get('note') or 'no note yet')}</i>"
            + ''.join(f'<br>• “{escape(c[:160])}”' for c in claims))
    card(f"{why}: {e['name']}", body, CHECKER, 'Open in checker')


def press(state: dict, n: int):
    from app.utils.store import write_json
    now = time.time()
    if n == 0:
        news = state.get('news') or {}
        card(f"{news.get('emoji', '📰')} {news.get('label', 'News day')}",
             escape(f"{news.get('story', '?')}: on {news.get('share', '?')}% of front pages, {news.get('age', '')}"),
             SITE + (f"#{news['anchor']}" if news.get('anchor') else ''), 'Open on bignews.day')
    elif n == 1 and state.get('born'):
        unseen = [e for e in state['born'] if e['id'] not in state.setdefault('seen', set())]
        e = unseen[-1] if unseen else state['born'][0]  # the oldest you haven't met, else the newest
        state['seen'].add(e['id'])
        write_json(os.path.join(Config.data, SEEN), sorted(state['seen']))
        motif_card(e, '🧬 Born today')
    elif n == 2 and state.get('retold'):
        e, k = state['retold'][int(now / 6) % len(state['retold'])]
        motif_card(e, f'🔝 Retold {k}× today')
    elif n == 3 and state.get('mood'):
        card('🌡 The front pages\' mood', '<br>'.join(f"{MOODS[m][0]} {m} {s:.0%}" for m, s in state['mood']))
    elif n == 4:
        from app import desk
        card('🎛 The machine', escape(desk.panel()).replace('\n', '<br>'))
    elif n == 5:
        from app import lights
        state['party_until'] = now + PARTY_SECONDS
        write_json(os.path.join(Config.data, lights.PARTY), {'until': state['party_until']})


# Running

def run(deck, start: str):
    from StreamDeck.ImageHelpers import PILHelper
    from app import lights, worker
    from app.utils.store import read_json
    state = {'seen': set(read_json(os.path.join(Config.data, SEEN), []))}
    deck.set_key_callback(lambda d, n, down: down and threading.Thread(target=press, args=(state, n), daemon=True).start())
    size = deck.key_image_format()['size']
    looked, bright = 0.0, None
    while True:
        if worker.commit() != start:
            logger.info("Deck: new code; exiting so systemd starts it again on it")
            return True
        now = time.time()
        if now - looked >= LOOK:
            look_up(state)
            looked = now
            want = DIM if lights.night() else BRIGHT
            if want != bright:
                deck.set_brightness(want)
                bright = want
        for n, img in enumerate(faces(state, size, now)):
            deck.set_key_image(n, PILHelper.to_native_key_format(deck, img))
        time.sleep(1)


def main():
    from StreamDeck.DeviceManager import DeviceManager
    from app import worker
    start = worker.commit()
    waiting = False
    while True:
        decks = DeviceManager().enumerate()
        if not decks:
            if not waiting:
                logger.info("Deck: no Stream Deck plugged in; waiting for one")
                waiting = True
            time.sleep(10)
            if worker.commit() != start:
                return
            continue
        waiting = False
        deck = decks[0]
        try:
            deck.open()
            deck.reset()
            logger.info("Deck: %s with %d keys", deck.deck_type(), deck.key_count())
            if run(deck, start):
                return
        except Exception as e:  # noqa: BLE001 - unplugged, or a USB hiccup: open it again
            logger.warning("Deck: %s", e)
            time.sleep(5)
        finally:
            try:
                deck.reset()
                deck.close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == '__main__':
    main()
