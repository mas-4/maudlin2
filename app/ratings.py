"""Outlet ratings, from ratings.csv at the repo root: partisan lean from AllSides' Media Bias Ratings (CC BY-NC 4.0)
and reliability from Wikipedia's Perennial sources list (CC BY-SA 4.0). They replace the Media Bias/Fact Check values
the scrapers used to carry, which weren't licensed for republishing.

AllSides rates on five levels; they're stored on the site's -3..3 lean scale as -2..2 (nothing is rated "extreme").
Outlets AllSides doesn't rate keep lean_rated False and a placeholder lean of 0: they're shown as "not rated" and left
out of every lean average."""
import csv
import os

from app.models import Session, Agency
from app.utils import Constants, get_logger

logger = get_logger(__name__)

RATINGS_FILE = os.path.join(Constants.Paths.ROOT, 'ratings.csv')
LEAN = {'Left': -2, 'Lean Left': -1, 'Center': 0, 'Lean Right': 1, 'Right': 2}
RELIABILITY = ['generally reliable', 'no consensus', 'generally unreliable', 'deprecated']


def load() -> dict[str, dict]:
    with open(RATINGS_FILE, newline='') as f:
        rows = csv.DictReader(line for line in f if not line.startswith('#'))
        return {r['outlet']: r for r in rows}


def apply() -> None:
    """Write the ratings onto every outlet in the database."""
    ratings = load()
    with Session() as s:
        for agency in s.query(Agency).all():
            r = ratings.get(agency.name, {})
            lean = (r.get('lean') or '').strip()
            if lean and lean not in LEAN:
                logger.warning("Unknown lean %r for %s in ratings.csv", lean, agency.name)
                lean = ''
            agency.lean_rated = bool(lean)
            agency._bias = LEAN.get(lean, 0)  # noqa prot attr
            agency.lean_url = (r.get('allsides_url') or '').strip() or None
            reliability = (r.get('reliability') or '').strip()
            agency.reliability = reliability if reliability in RELIABILITY else None
            agency.reliability_note = (r.get('reliability_note') or '').strip() or None
            if not r:
                logger.warning("%s isn't in ratings.csv; showing it as not rated", agency.name)
        s.commit()


def unrated() -> set[str]:
    """Outlets with no lean rating."""
    with Session() as s:
        return {a.name for a in s.query(Agency).filter(Agency.lean_rated.is_(False)).all()}
