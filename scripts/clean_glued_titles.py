"""Headlines stored with a byline, section label or view count glued on (Oct 28): Red State and Townhall cards
("Polling  This Gallup Poll Shows…  Amy Curtis"), Scripps News promos ("Sports  …  Justin Boggs") and The Gateway
Pundit's trending list ("86.3K views  Translation Reveals…"). The scrapers now take these parts out of the link;
this re-reads the stored link html of older rows the same way and rewrites their title and processed text.

Only the title and processed text change: the scores the language model gave the glued wording stay, and a row that
now reads the same as another of its article's headlines stays a row of its own.

    python scripts/clean_glued_titles.py                    what it would change (the live database, read only)
    python scripts/clean_glued_titles.py --db PATH          the same on another copy
    python scripts/clean_glued_titles.py --db PATH --apply  change them (back the database up first)"""
import argparse
import os
import sqlite3
import sys

from bs4 import BeautifulSoup as Soup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.analysis.preprocessing import extract_text, preprocess  # noqa: E402
from app.scraper import without  # noqa: E402
from app.scrapers.townhall import CARD_EXTRAS  # noqa: E402
from app.utils import Config  # noqa: E402

PARTS = {'Red State': CARD_EXTRAS, 'Townhall': CARD_EXTRAS, 'Scripps News': '.promo__category, .promo__author',
         'The Gateway Pundit': '[data-pa-f="views"], .pa-trending__views'}


def changes(con: sqlite3.Connection):
    """(headline id, old title, new title) for every stored headline whose link html has parts to take out"""
    marks = ('th-ts-by', 'th-brk-by', 'th-ts-eye', 'th-brk-eye', 'promo__author', 'promo__category',
             'pa-trending__views')
    where = ' or '.join('h.raw like ?' for _ in marks)
    rows = con.execute(f"""select h.id, ag.name, h.title, h.raw from headline h join article a on a.id = h.article_id
        join agency ag on ag.id = a.agency_id where ag.name in ({','.join('?' * len(PARTS))}) and ({where})""",
                       [*PARTS, *(f'%{m}%' for m in marks)]).fetchall()
    for hid, agency, title, raw in rows:
        link = Soup(raw, 'html.parser')
        new = ' '.join(extract_text(without(link, PARTS[agency])).split())
        if new and new != ' '.join(title.split()):
            yield hid, title, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=Config.db_file_path)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    uri = f'file:{args.db}' + ('' if args.apply else '?mode=ro')
    con = sqlite3.connect(uri, uri=True)
    found = list(changes(con))
    for hid, old, new in found[:10]:
        print(f'{hid}: {" ".join(old.split())!r}\n    -> {new!r}')
    print(f'{len(found)} headlines to clean')
    if not args.apply:
        print('nothing changed: run with --apply to rewrite them')
        return
    con.executemany('update headline set title = ?, processed = ? where id = ?',
                    [(new, preprocess(new), hid) for hid, _, new in found])
    con.commit()
    print(f'rewrote {len(found)}')


if __name__ == '__main__':
    main()
