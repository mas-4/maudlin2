"""Share images: the picture a link to the site shows on Bluesky, Mastodon and the rest (og:image), drawn in the site's
look (docs/style-book.md: a white card, an ink outline, a hard colored shadow, Comic Neue, emoji, a little tilt).

Each kind of page gets a card that shows that page, with a picture of its own (Oct 27, the person, of a saga link that
showed the site's card: "doesn't even match the shared page, it's generic and lame"):
- a saga: its name, its parts' coverage over time as a river in the parts' colors, its parts, outlets and lean;
- a story: its headline, how many front pages carried it hour by hour, its lean and the motif it's told as;
- a motif: its name and note, a teller's own words for it, and the shows it came up on by side;
- the front page: the top stories right now, each with its lean;
- every other page: the site's own card.
A phone shows a card about a third of its size, so nothing on one is smaller than ~26px.

Drawn once per look: a card is cached under its contents' hash, so an hourly build only draws what changed, and an
unchanged card keeps its bytes (Netlify uploads only changed files)."""
import hashlib
import json
import os
import shutil
import time
from datetime import datetime
from functools import lru_cache

import pytz
from PIL import Image, ImageDraw, ImageFont

from app.utils.config import Config

W, H = 1200, 630  # the size Bluesky, Mastodon and the rest crop to without losing the edges
INK = (31, 31, 46)
GREY = (85, 85, 85)
POPS = {'pink': (255, 79, 163), 'yellow': (255, 196, 0), 'teal': (0, 194, 168), 'blue': (58, 134, 255),
        'orange': (255, 107, 26), 'purple': (138, 92, 255)}
# Lean colors as the site draws them (graphing.bias_colors' ends and middle)
LEAN = {'left': (38, 53, 122), 'center': (160, 160, 170), 'right': (122, 2, 25)}
PART_COLORS = ['#ff4fa3', '#00c2a8', '#ffc400', '#3a86ff', '#ff6b1a', '#8a5cff']  # story_charts.PART_COLORS
FOLDER = 'share'  # in the build: /share/<hash>.png
VERSION = 4  # bump to redraw every card after a change to the drawing
FONT_FILES = {'bold': ['/usr/share/fonts/comic-neue/ComicNeue-Bold.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'],
              'regular': ['/usr/share/fonts/comic-neue/ComicNeue-Regular.ttf', '/usr/share/fonts/TTF/DejaVuSans.ttf'],
              # big numbers on stickers: the site shouts them in Bungee, which isn't installed for drawing here
              'black': ['/usr/share/fonts/noto/NotoSans-Black.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf']}
EMOJI_FONT = '/usr/share/fonts/noto/NotoColorEmoji.ttf'  # a bitmap font: drawn at its one size, then scaled
MOTTO = 'The news, and the stories people tell about it'
CARD = (60, 60, W - 60, H - 60)  # the white card; everything is drawn inside it
KEEP_DAYS = 3  # a cached card no build has used for this long is deleted (a live story's card changes every hour)


def rgb(color) -> tuple:
    if isinstance(color, tuple):
        return color
    if color in POPS:
        return POPS[color]
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def tint(color, amount: float) -> tuple:
    """`color` mixed into white: the site's sticker and card tints (color-mix 10-25%)"""
    return tuple(round(255 - (255 - c) * amount) for c in rgb(color))


def eastern(t: datetime) -> datetime:
    """A database time (naive, UTC) in US Eastern"""
    return (pytz.utc.localize(t) if t.tzinfo is None else t).astimezone(pytz.timezone('US/Eastern'))


def cache_dir() -> str:
    return os.path.join(Config.data, 'share_cache')


@lru_cache(maxsize=64)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_FILES[weight]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


@lru_cache(maxsize=64)
def emoji(char: str, size: int) -> Image.Image | None:
    """An emoji as a picture `size` pixels across (None where the emoji font is missing: the card goes without)"""
    try:
        f = ImageFont.truetype(EMOJI_FONT, 109)  # Noto Color Emoji's only size
    except OSError:
        return None
    im = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((100, 100), char, font=f, embedded_color=True, anchor='mm')
    box = im.getbbox()
    if not box:
        return None
    im = im.crop(box)
    scale = size / max(im.size)
    return im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)


def put_emoji(img: Image.Image, char: str, x: float, y: float, size: int):
    """An emoji centered on (x, y)"""
    e = emoji(char, size)
    if e:
        img.paste(e, (round(x - e.width / 2), round(y - e.height / 2)), e)


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if draw.textlength(trial, font=f) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit(draw, text: str, weight: str, sizes: tuple, width: int, most: int) -> tuple:
    """The biggest of `sizes` at which `text` wraps into `most` lines or fewer; at the smallest, cut with an ellipsis"""
    for size in sizes:
        f = font(weight, size)
        lines = wrap(draw, text, f, width)
        if len(lines) <= most:
            return f, lines
    lines = lines[:most]
    while lines and draw.textlength(lines[-1] + '…', font=f) > width:
        lines[-1] = lines[-1].rsplit(' ', 1)[0]
    lines[-1] = lines[-1].rstrip(',;:') + '…'
    return f, lines


def cut(draw, text: str, f, width: int) -> str:
    """`text` on one line, cut with an ellipsis where it's too long"""
    if draw.textlength(text, font=f) <= width:
        return text
    while text and draw.textlength(text + '…', font=f) > width:
        text = text[:-1]
    return text.rstrip(' ,;:') + '…'


def frame(pop, seed: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A white canvas with Memphis shapes in the corners and a squiggle, and the card with its hard shadow"""
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    h = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    shapes = list(POPS.values())
    for i, (x, y) in enumerate(((40, 40), (1150, 70), (60, 590), (1130, 585), (600, 22))):
        c = shapes[(h >> (i * 3)) % len(shapes)]
        r = 18 + (h >> (i * 5)) % 22
        if (h >> i) & 1:
            d.ellipse((x - r, y - r, x + r, y + r), fill=c, outline=INK, width=3)
        else:
            d.polygon(((x, y - r), (x + r, y + r), (x - r, y + r)), fill=c, outline=INK, width=3)
    squiggle = shapes[(h >> 17) % len(shapes)]
    d.line([(860 + 22 * k, 34 if k % 2 else 18) for k in range(7)], fill=squiggle, width=7, joint='curve')
    d.rounded_rectangle((CARD[0] + 14, CARD[1] + 14, CARD[2] + 14, CARD[3] + 14), radius=28, fill=rgb(pop))  # no blur
    d.rounded_rectangle(CARD, radius=28, fill='white', outline=INK, width=6)
    return img, d


def tilted(img: Image.Image, layer: Image.Image, x: float, y: float, angle: float):
    """Paste `layer` with its top-left near (x, y), turned `angle` degrees (the site's stickers tilt 1-5°)"""
    turned = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    img.paste(turned, (round(x - (turned.width - layer.width) / 2), round(y - (turned.height - layer.height) / 2)), turned)


def pill(img: Image.Image, x: float, y: float, text: str, icon: str = '', pop='yellow', size: int = 30,
         angle: float = -2, fill=None) -> float:
    """A pill-shaped label with an emoji, tilted; returns its width"""
    f = font('bold', size)
    probe = ImageDraw.Draw(img)
    pad, gap = 20, (size + 10 if icon else 0)
    w = round(pad * 2 + gap + probe.textlength(text, font=f))
    h = size + 22
    layer = Image.new('RGBA', (w + 8, h + 8), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((0, 0, w, h), radius=h // 2, fill=rgb(fill) if fill else rgb(pop), outline=INK, width=4)
    if icon:
        e = emoji(icon, size + 4)
        if e:
            layer.paste(e, (pad - 4, round(h / 2 - e.height / 2)), e)
    ld.text((pad + gap, h / 2 + 1), text, font=f, fill=INK, anchor='lm')
    tilted(img, layer, x, y, angle)
    return w


def kicker(img: Image.Image, text: str, icon: str, pop='yellow'):
    pill(img, 96, 88, text, icon, pop, 30, -2)


def brand(img: Image.Image, d: ImageDraw.ImageDraw):
    """The site's name in the card's top right corner, with its emoji"""
    f = font('bold', 36)
    right = CARD[2] - 40
    width = d.textlength('bignews.day', font=f)
    d.text((right, 116), 'bignews.day', font=f, fill=INK, anchor='rm')
    put_emoji(img, '🗞️', right - width - 30, 114, 40)


def sticker(img: Image.Image, x: float, y: float, w: int, h: int, icon: str, big: str, small: str, pop,
            angle: float = 0):
    """A sticker: a tinted card with a hard shadow, a big emoji, a big number and a word or two"""
    layer = Image.new('RGBA', (w + 10, h + 10), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((8, 8, w + 8, h + 8), radius=16, fill=rgb(pop))
    ld.rounded_rectangle((0, 0, w, h), radius=16, fill=tint(pop, 0.2), outline=INK, width=4)
    e = emoji(icon, h - 26) if icon else None
    left = 14
    if e:
        layer.paste(e, (left, round(h / 2 - e.height / 2)), e)
        left += e.width + 12
    fb = font('black', 40 if h >= 80 else 34)
    ld.text((left, h / 2 - (14 if small else 0)), big, font=fb, fill=INK, anchor='lm')
    if small:
        ld.text((left + 2, h / 2 + 24), small, font=font('bold', 24), fill=INK, anchor='lm')
    tilted(img, layer, x, y, angle)


def lean_bar(img: Image.Image, d: ImageDraw.ImageDraw, counts: dict, x: int, y: int, width: int, height: int = 50):
    """Left, center and right in the lean colors, a donkey at the left end and an elephant at the right"""
    put_emoji(img, '🫏', x + 22, y + height / 2, 42)
    put_emoji(img, '🐘', x + width - 22, y + height / 2, 42)
    x, width = x + 54, width - 108
    total = sum(counts.get(k, 0) for k in LEAN) or 1
    at = x
    for k in ('left', 'center', 'right'):
        n = counts.get(k, 0)
        if not n:
            continue
        w = round(width * n / total)
        d.rectangle((at, y, at + w, y + height), fill=LEAN[k])
        f = font('black', 28 if w > 60 else 22)
        if w >= d.textlength(str(n), font=f) + 10:  # every side's count shown wherever it fits, so no side loses its number
            d.text((at + w / 2, y + height / 2), str(n), font=f, fill='white' if k != 'center' else INK, anchor='mm')
        at += w
    d.rectangle((x, y, x + width, y + height), outline=INK, width=4)


def bubble(img: Image.Image, x: float, y: float, text: str, max_w: int, angle: float = 1.5):
    """A teller's own words in a speech bubble"""
    probe = ImageDraw.Draw(img)
    f, lines = fit(probe, f'“{text}”', 'bold', (40, 36, 32), max_w - 60, 1)
    w = round(probe.textlength(lines[0], font=f)) + 60
    h = f.size + 34
    layer = Image.new('RGBA', (w + 12, h + 40), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    tail = [(40, h - 4), (30, h + 30), (78, h - 4)]
    ld.rounded_rectangle((8, 8, w + 8, h + 8), radius=24, fill=POPS['yellow'])
    ld.polygon([(px + 8, py + 8) for px, py in tail], fill=POPS['yellow'])
    ld.rounded_rectangle((0, 0, w, h), radius=24, fill='white', outline=INK, width=4)
    ld.polygon(tail, fill='white')
    ld.line([tail[0], tail[1], tail[2]], fill=INK, width=4, joint='curve')
    ld.text((30, h / 2 + 1), lines[0], font=f, fill=INK, anchor='lm')
    tilted(img, layer, x, y, angle)


def river(d: ImageDraw.ImageDraw, layers: list[list[float]], colors: list, box: tuple):
    """Coverage over time, each layer stacked on the ones before (a saga's parts), outlined in ink"""
    x0, y0, x1, y1 = box
    n = len(layers[0]) if layers else 0
    if n < 2:
        return
    tops = [sum(layer[i] for layer in layers) for i in range(n)]
    peak = max(tops) or 1
    X = lambda i: x0 + (x1 - x0) * i / (n - 1)
    Y = lambda v: y1 - (y1 - y0) * v / peak
    below = [0.0] * n
    for layer, color in zip(layers, colors):
        above = [below[i] + layer[i] for i in range(n)]
        if any(layer):
            d.polygon([(X(i), Y(above[i])) for i in range(n)] + [(X(i), Y(below[i])) for i in reversed(range(n))],
                      fill=rgb(color))
        below = above
    d.line([(X(i), Y(tops[i])) for i in range(n)], fill=INK, width=4, joint='curve')
    d.line([(x0, y1), (x1, y1)], fill=INK, width=4)


def area(d: ImageDraw.ImageDraw, values: list[float], color, box: tuple) -> tuple:
    """One series as a tinted area under an ink line; returns the peak's (x, y, value)"""
    x0, y0, x1, y1 = box
    n = len(values)
    peak = max(values) or 1
    X = lambda i: x0 + (x1 - x0) * i / max(1, n - 1)
    Y = lambda v: y1 - (y1 - y0) * v / peak
    pts = [(X(i), Y(v)) for i, v in enumerate(values)]
    d.polygon(pts + [(x1, y1), (x0, y1)], fill=tint(color, 0.35))
    d.line(pts, fill=INK, width=4, joint='curve')
    d.line([(x0, y1), (x1, y1)], fill=INK, width=4)
    i = max(range(n), key=lambda k: values[k])
    return pts[i][0], pts[i][1], values[i]


def title(d: ImageDraw.ImageDraw, text: str, sizes: tuple, most: int, y: int = 166, width: int = 1000) -> int:
    """The card's big words from `y`; returns where they end"""
    f, lines = fit(d, text, 'bold', sizes, width, most)
    for line in lines:
        d.text((100, y), line, font=f, fill=INK)
        y += f.size + 6
    return y


def cached(kind: str, spec: dict, draw) -> str:
    """The card for `spec`, drawn by draw(spec) unless a card for the same spec is already cached: its path in the build"""
    digest = hashlib.sha1(json.dumps([VERSION, kind, spec], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    name = f'{kind}-{digest}.png'
    os.makedirs(cache_dir(), exist_ok=True)
    kept = os.path.join(cache_dir(), name)
    if not os.path.exists(kept):
        # 256 colors: a card is flat color and text, so a palette keeps it sharp at a third of the bytes
        draw(spec).quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(kept, optimize=True)
    else:
        os.utime(kept)  # used this build: kept from pruning
    out = os.path.join(Config.build, FOLDER)
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(kept, os.path.join(out, name))
    return f'{FOLDER}/{name}'


def prune(days: float = KEEP_DAYS):
    """Delete cached cards no build has used for `days` (run before a build draws its cards)"""
    if not os.path.isdir(cache_dir()):
        return
    cutoff = time.time() - days * 86400
    for name in os.listdir(cache_dir()):
        path = os.path.join(cache_dir(), name)
        if os.path.getmtime(path) < cutoff:
            os.remove(path)


def site_card() -> str:
    """The site's own card, for pages without one of their own"""
    def draw(spec):
        img, d = frame('pink', 'site')
        layer = Image.new('RGBA', (220, 220), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle((12, 12, 212, 212), radius=36, fill=POPS['pink'])
        ld.rounded_rectangle((0, 0, 200, 200), radius=36, fill=POPS['yellow'], outline=INK, width=6)
        e = emoji('🗞️', 140)
        if e:
            layer.paste(e, (100 - e.width // 2, 100 - e.height // 2), e)
        tilted(img, layer, 100, 120, -5)
        d.text((350, 150), 'bignews.day', font=font('bold', 96), fill=INK)
        f, lines = fit(d, spec['line'], 'bold', (44, 40, 36), 720, 2)
        y = 266
        for line in lines:
            d.text((352, y), line, font=f, fill=GREY)
            y += f.size + 6
        for i, (icon, big, small, pop) in enumerate(spec['stickers']):
            sticker(img, 100 + i * 340, 420, 310, 96, icon, big, small, pop, (-2, 1.5, -1)[i % 3])
        return img
    return cached('site', {'line': MOTTO,
                           'stickers': [('📰', '145', 'front pages, hourly', 'blue'),
                                        ('🎙️', '100+', 'shows, left and right', 'teal'),
                                        ('🧩', '1,000', 'story shapes', 'purple')]}, draw)


def front_card(stories: list[dict], when: str) -> str:
    """The front page's card: the top stories right now, each with its lean. stories: [{label, outlets, leans}]"""
    def draw(spec):
        img, d = frame('yellow', 'front')
        kicker(img, 'THE FRONT PAGES RIGHT NOW', '📰', 'yellow')
        brand(img, d)
        y = 170
        for i, st in enumerate(spec['stories'][:3]):
            badge = Image.new('RGBA', (70, 70), (0, 0, 0, 0))
            bd = ImageDraw.Draw(badge)
            bd.ellipse((0, 0, 64, 64), fill=rgb(PART_COLORS[i]), outline=INK, width=4)
            bd.text((32, 33), str(i + 1), font=font('black', 34), fill=INK, anchor='mm')
            img.paste(badge, (100, y + 10), badge)
            f, lines = fit(d, st['label'], 'bold', (36, 32, 30), 640, 2)
            ty = y + (4 if len(lines) == 2 else 22)
            for line in lines:
                d.text((186, ty), line, font=f, fill=INK)
                ty += f.size + 4
            d.text((1100, y + 14), f"{st['outlets']} front pages", font=font('bold', 24), fill=GREY, anchor='rm')
            lean_bar(img, d, st['leans'], 850, y + 36, 250, 40)
            y += 104
        d.text((100, H - 104), spec['when'], font=font('bold', 28), fill=GREY, anchor='lm')
        return img
    return cached('front', {'stories': [{'label': s['label'], 'outlets': s['outlets'],
                                         'leans': {k: s['leans'].get(k, 0) for k in LEAN}} for s in stories],
                            'when': when}, draw)


def motif_card(name: str, note: str, genre: str, leans: dict, phrase: str | None = None) -> str:
    def draw(spec):
        img, d = frame('purple', spec['name'])
        kicker(img, 'STORY SHAPE' + (f' · {spec["genre"].upper()}' if spec['genre'] else ''), '🧩', 'teal')
        brand(img, d)
        y = title(d, spec['name'], (84, 72, 62, 54), 2)
        f2, lines2 = fit(d, spec['note'], 'regular', (34, 31, 28) if spec['phrase'] else (38, 34, 31), 1000,
                         2 if spec['phrase'] else 3)
        y += 6
        for line in lines2:
            d.text((100, y), line, font=f2, fill=GREY)
            y += f2.size + 6
        if spec['phrase']:
            bubble(img, 96, y + 16, spec['phrase'], 1000)
        shows = [(k, v) for k, v in spec['leans'].items() if v]
        bottom = H - 130
        if shows:  # "came up on", as the site says it: a show may have told it, reported it or argued against it
            f = font('bold', 30)
            d.text((100, bottom), 'came up on', font=f, fill=INK, anchor='lm')
            x = 100 + d.textlength('came up on', font=f) + 16
            icons = {'left': '🫏', 'center': '⚖️', 'right': '🐘'}
            for i, (k, v) in enumerate(shows):
                x += pill(img, x, bottom - 26, f'{v} {k}', icons[k], fill=tint(LEAN[k], 0.22), size=28,
                          angle=(-2, 1.5, -1)[i]) + 14
            total = sum(v for _, v in shows)
            d.text((x + 4, bottom), 'show' if total == 1 else 'shows', font=f, fill=INK, anchor='lm')
            d.text((100, bottom + 48), 'a story people tell, not a claim that it\'s true', font=font('bold', 26),
                   fill=GREY, anchor='lm')
        else:
            d.text((100, bottom + 20), 'a story people tell, not a claim that it\'s true', font=font('bold', 30),
                   fill=GREY, anchor='lm')
        return img
    return cached('motif', {'name': name, 'note': note, 'genre': genre, 'leans': leans, 'phrase': phrase or ''}, draw)


def story_card(label: str, outlets: int, lean_counts: dict, hours: str, spark: list[float] | None = None,
               told: str | None = None) -> str:
    def draw(spec):
        img, d = frame('pink', spec['label'])
        kicker(img, 'STORY FILE', '🗞️', 'yellow')
        brand(img, d)
        has_spark = len(spec['spark']) >= 3
        y = title(d, spec['label'], (60, 54, 48, 44) if has_spark else (72, 64, 56, 50), 2 if has_spark else 3)
        if has_spark:
            top = max(y + 6, 250)
            box = (100, top + 48, 1100, 420)  # the peak's label sits in the 48px above the curve
            px, py, peak = area(d, spec['spark'], 'pink', box)
            text = f'peak: {peak:g} front pages'
            f = font('bold', 28)
            tx = min(max(px - d.textlength(text, font=f) / 2, 110), 1090 - d.textlength(text, font=f))
            d.rounded_rectangle((tx - 10, py - 46, tx + d.textlength(text, font=f) + 10, py - 8), radius=10,
                                fill='white', outline=INK, width=3)
            d.text((tx, py - 27), text, font=f, fill=INK, anchor='lm')
        row = 438
        if spec['told']:
            pill(img, 96, row, f"being told as “{spec['told']}”", '🧩', fill=tint('purple', 0.25), size=28, angle=1.5)
        line = f"{spec['outlets']} outlets" + (f" · {spec['hours']} on the front pages" if spec['hours'] else '')
        d.text((1100, row + 26), line, font=font('bold', 28), fill=GREY, anchor='rm')
        lean_bar(img, d, spec['leans'], 100, 496, 1000, 46)
        return img
    return cached('story', {'label': label, 'outlets': outlets, 'hours': hours, 'told': told or '',
                            'spark': [round(v) for v in (spark or [])],
                            'leans': {k: lean_counts.get(k, 0) for k in LEAN}}, draw)


def saga_card(name: str, color: str, first: datetime, last: datetime, parts: int, outlets: int, leans: dict,
              layers: list[list[float]], told: str | None = None) -> str:
    """A saga's card: its name, its parts' coverage over time as a river (layers: outlets per time step, a list per
    part in the parts' order), its parts, outlets and lean"""
    first, last = eastern(first), eastern(last)  # the site's dates are Eastern; the database's are UTC
    days = max(1, (last.date() - first.date()).days + 1)

    def draw(spec):
        img, d = frame(spec['color'], spec['name'])
        kicker(img, f"SAGA · {spec['days']} DAY{'S' if spec['days'] != 1 else ''} · {spec['parts']} PARTS", '🧵',
               'pink')
        brand(img, d)
        y = title(d, spec['name'], (72, 64, 56, 50), 2)
        if spec['layers'] and len(spec['layers'][0]) >= 2:
            river(d, spec['layers'], PART_COLORS * 3, (100, max(y + 16, 290), 1100, 420))
        row = 436
        if spec['told']:
            pill(img, 96, row, f"being told as “{spec['told']}”", '🧩', fill=tint('purple', 0.25), size=28, angle=1.5)
        d.text((1100, row + 26), f"{spec['span']} · {spec['outlets']} outlets", font=font('bold', 28), fill=GREY,
               anchor='rm')
        lean_bar(img, d, spec['leans'], 100, 496, 1000, 46)
        return img
    span = f"{first.strftime('%b %-d')} – {last.strftime('%b %-d')}" if days > 1 else first.strftime('%b %-d')
    return cached('saga', {'name': name, 'color': color, 'days': days, 'parts': parts, 'outlets': outlets,
                           'leans': {k: leans.get(k, 0) for k in LEAN}, 'span': span, 'told': told or '',
                           'layers': [[round(v, 1) for v in layer] for layer in layers]}, draw)
