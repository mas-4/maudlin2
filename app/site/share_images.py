"""Share images: the picture a link to the site shows on Bluesky, Mastodon and the rest (og:image), drawn in the site's
look (docs/style-book.md: a white card, an ink outline, a hard colored shadow, Comic Neue). One for the site, one per
story page and one per motif page. Drawn once per look: a card is cached under its contents' hash, so an hourly build
only draws what changed, and an unchanged card keeps its bytes (Netlify uploads only changed files)."""
import hashlib
import json
import os
import shutil
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.utils.config import Config

W, H = 1200, 630  # the size Bluesky, Mastodon and the rest crop to without losing the edges
INK = (31, 31, 46)
GREY = (85, 85, 85)
POPS = {'pink': (255, 79, 163), 'yellow': (255, 196, 0), 'teal': (0, 194, 168), 'blue': (58, 134, 255),
        'orange': (255, 107, 26), 'purple': (138, 92, 255)}
# Lean colors as the site draws them (graphing.bias_colors' ends and middle)
LEAN = {'left': (38, 53, 122), 'center': (160, 160, 170), 'right': (122, 2, 25)}
FOLDER = 'share'  # in the build: /share/<hash>.png
VERSION = 3  # bump to redraw every card after a change to the drawing
FONT_FILES = {'bold': ['/usr/share/fonts/comic-neue/ComicNeue-Bold.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'],
              'regular': ['/usr/share/fonts/comic-neue/ComicNeue-Regular.ttf', '/usr/share/fonts/TTF/DejaVuSans.ttf']}


def cache_dir() -> str:
    return os.path.join(Config.data, 'share_cache')


@lru_cache(maxsize=64)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_FILES[weight]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


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


def frame(pop: str, seed: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A white canvas with a few Memphis shapes in the corners, and the card with its hard shadow"""
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    h = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    shapes = list(POPS.values())
    for i, (x, y) in enumerate(((40, 40), (1150, 70), (60, 590), (1130, 585), (600, 22))):
        c = shapes[(h >> (i * 3)) % len(shapes)]
        r = 18 + (h >> (i * 5)) % 22
        if (h >> i) & 1:
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)
        else:
            d.polygon(((x, y - r), (x + r, y + r), (x - r, y + r)), fill=c)
    d.rounded_rectangle((74, 74, W - 46, H - 46), radius=28, fill=POPS[pop])  # the hard shadow, no blur
    d.rounded_rectangle((60, 60, W - 60, H - 60), radius=28, fill='white', outline=INK, width=6)
    return img, d


def kicker(d: ImageDraw.ImageDraw, text: str, pop: str = 'yellow'):
    f = font('bold', 30)
    width = d.textlength(text, font=f)
    d.rounded_rectangle((100, 92, 100 + width + 36, 142), radius=25, fill=POPS[pop], outline=INK, width=4)
    d.text((118, 117), text, font=f, fill=INK, anchor='lm')


def footer(d: ImageDraw.ImageDraw, text: str):
    d.text((W - 100, H - 98), 'bignews.day', font=font('bold', 32), fill=INK, anchor='rm')
    if text:
        d.text((100, H - 98), text, font=font('bold', 28), fill=GREY, anchor='lm')


def lean_bar(d, counts: dict, x: int, y: int, width: int, height: int = 34):
    total = sum(counts.get(k, 0) for k in LEAN) or 1
    at = x
    for k in ('left', 'center', 'right'):
        n = counts.get(k, 0)
        if not n:
            continue
        w = round(width * n / total)
        d.rectangle((at, y, at + w, y + height), fill=LEAN[k])
        if w > 60:
            d.text((at + w / 2, y + height / 2), str(n), font=font('bold', 24), fill='white', anchor='mm')
        at += w
    d.rectangle((x, y, x + width, y + height), outline=INK, width=3)


def cached(kind: str, spec: dict, draw) -> str:
    """The card for `spec`, drawn by draw(spec) unless a card for the same spec is already cached: its path in the build"""
    digest = hashlib.sha1(json.dumps([VERSION, kind, spec], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    name = f'{kind}-{digest}.png'
    os.makedirs(cache_dir(), exist_ok=True)
    kept = os.path.join(cache_dir(), name)
    if not os.path.exists(kept):
        # 256 colors: a card is flat color and text, so a palette keeps it sharp at a third of the bytes
        draw(spec).quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(kept, optimize=True)
    out = os.path.join(Config.build, FOLDER)
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(kept, os.path.join(out, name))
    return f'{FOLDER}/{name}'


def site_card() -> str:
    def draw(spec):
        img, d = frame('pink', 'site')
        kicker(d, 'BIGNEWS.DAY')
        f, lines = fit(d, spec['line'], 'bold', (76, 68, 60), 900, 3)
        y = 200
        for line in lines:
            d.text((100, y), line, font=f, fill=INK)
            y += f.size + 14
        f2, lines2 = fit(d, spec['sub'], 'regular', (36, 32), 980, 3)
        y += 24
        for line in lines2:
            d.text((100, y), line, font=f2, fill=GREY)
            y += f2.size + 10
        footer(d, '')
        return img
    return cached('site', {'line': 'The news, and the stories people tell about it',
                           'sub': '145 front pages every hour, TV, radio and 100+ shows left and right, '
                                  'and a folklorist\'s index of the stories being told.'}, draw)


def motif_card(name: str, note: str, genre: str, leans: dict) -> str:
    def draw(spec):
        img, d = frame('purple', spec['name'])
        kicker(d, 'BND MOTIF INDEX' + (f' · {spec["genre"].upper()}' if spec['genre'] else ''), 'teal')
        f, lines = fit(d, spec['name'], 'bold', (84, 72, 62, 54), 1000, 2)
        y = 178
        for line in lines:
            d.text((100, y), line, font=f, fill=INK)
            y += f.size + 8
        y += 18
        f2, lines2 = fit(d, spec['note'], 'regular', (36, 33, 30), 1000, 7 if len(lines) == 1 else 6)
        for line in lines2:
            if y + f2.size > H - 150:
                break
            d.text((100, y), line, font=f2, fill=GREY)
            y += f2.size + 8
        shows = {k: v for k, v in spec['leans'].items() if v}
        if shows:
            text = 'came up on ' + ', '.join(f'{v} {k}' for k, v in shows.items()) + \
                   (' show' if sum(shows.values()) == 1 else ' shows')
            footer(d, text)
        else:
            footer(d, 'a story people tell, not a claim that it\'s true')
        return img
    return cached('motif', {'name': name, 'note': note, 'genre': genre, 'leans': leans}, draw)


def story_card(label: str, outlets: int, lean_counts: dict, hours: str) -> str:
    def draw(spec):
        img, d = frame('pink', spec['label'])
        kicker(d, 'STORY FILE')
        f, lines = fit(d, spec['label'], 'bold', (72, 64, 56, 50), 1000, 3)
        y = 180
        for line in lines:
            d.text((100, y), line, font=f, fill=INK)
            y += f.size + 8
        lean_bar(d, spec['leans'], 100, max(y + 24, H - 200), 1000)  # left, center, right, in the lean colors
        footer(d, f"{spec['outlets']} outlets carried it" + (f" · {spec['hours']} on the front pages" if spec['hours'] else ''))
        return img
    return cached('story', {'label': label, 'outlets': outlets, 'hours': hours,
                            'leans': {k: lean_counts.get(k, 0) for k in LEAN}}, draw)
