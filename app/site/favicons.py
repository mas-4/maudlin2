"""Each outlet's own icon, for its chips around the site. Fetched from the outlet's homepage (its apple-touch-icon or
<link rel="icon">, else /favicon.ico), shrunk to a small PNG and cached under data/, refreshed weekly. The build copies
them in, so readers' browsers load them from our site and no third party sees the page views."""
import io
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urljoin

import requests as rq
from bs4 import BeautifulSoup
from PIL import Image

from app.models import Session, Agency
from app.utils import Config, Constants, get_logger

logger = get_logger(__name__)

CACHE = os.path.join(Constants.Paths.ROOT, 'data', 'favicons')
BUILD_DIR = 'icons'  # under the build
MAX_AGE = 7 * 24 * 3600
SIZE = 64
TIMEOUT = 15


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def _candidates(home: str) -> list[str]:
    """Icon URLs from the homepage's <link> tags, biggest-looking first, then /favicon.ico."""
    found = []
    try:
        page = rq.get(home, headers=Constants.Headers.firefox, timeout=TIMEOUT)
        soup = BeautifulSoup(page.text, 'html.parser')
        for link in soup.find_all('link', href=True):
            rel = ' '.join(link.get('rel', [])).lower()
            if 'icon' not in rel or 'mask-icon' in rel:
                continue
            sizes = re.findall(r'(\d+)x\d+', link.get('sizes', '') or '')
            size = max(map(int, sizes)) if sizes else (180 if 'apple' in rel else 32)
            found.append((size, urljoin(page.url, link['href'])))
    except rq.RequestException:
        pass
    found.sort(key=lambda x: -x[0])
    return [url for _, url in found if not url.endswith('.svg')] + [urljoin(home, '/favicon.ico')]


def _fetch(home: str) -> Optional[Image.Image]:
    for url in _candidates(home):
        try:
            response = rq.get(url, headers=Constants.Headers.firefox, timeout=TIMEOUT)
            if not response.ok or not response.content:
                continue
            image = Image.open(io.BytesIO(response.content))
            if hasattr(image, 'ico'):  # an .ico holds several sizes; take the biggest
                image.size = max(image.ico.sizes())
            image = image.convert('RGBA')
            if min(image.size) < 16:
                continue
            image.thumbnail((SIZE, SIZE), Image.LANCZOS)
            return image
        except (rq.RequestException, OSError, ValueError):
            continue
    return None


def refresh(force: bool = False) -> None:
    """Fetch icons that are missing or more than a week old."""
    os.makedirs(CACHE, exist_ok=True)
    with Session() as s:
        agencies = [(a.name, a.url) for a in s.query(Agency).all()]

    def stale(name):
        path = os.path.join(CACHE, f'{slug(name)}.png')
        miss = os.path.join(CACHE, f'{slug(name)}.missing')  # tried and found nothing; also retried weekly
        newest = max((os.path.getmtime(p) for p in (path, miss) if os.path.exists(p)), default=0)
        return force or time.time() - newest > MAX_AGE

    todo = [(n, u) for n, u in agencies if stale(n)]
    if not todo:
        return
    logger.info("Fetching icons for %i outlets", len(todo))

    def one(item):
        name, home = item
        image = _fetch(home)
        if image is None:
            open(os.path.join(CACHE, f'{slug(name)}.missing'), 'w').close()
            return False
        image.save(os.path.join(CACHE, f'{slug(name)}.png'))
        return True

    with ThreadPoolExecutor(8) as pool:
        got = sum(pool.map(one, todo))
    logger.info("Got %i of %i outlet icons", got, len(todo))


def publish() -> dict[str, str]:
    """Copy the cached icons into the build; returns outlet name -> icon path for the templates."""
    out = os.path.join(Config.build, BUILD_DIR)
    os.makedirs(out, exist_ok=True)
    icons = {}
    with Session() as s:
        names = [a.name for a in s.query(Agency).all()]
    for name in names:
        src = os.path.join(CACHE, f'{slug(name)}.png')
        if os.path.exists(src):
            shutil.copy(src, out)
            icons[name] = f'{BUILD_DIR}/{slug(name)}.png'
    return icons
