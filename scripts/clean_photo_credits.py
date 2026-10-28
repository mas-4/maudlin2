"""Photo credits stored as headlines (Oct 28): NBC News, CNN, ABC News and The Christian Science Monitor link each
story's photo on its own, with the photo's credit inside the link, so the link read as "Saul Loeb / AFP via Getty"
and was kept as a headline, often as its article's first. Bloomberg's front page did the same until it moved to its
feeds (Oct 11). The scrapers now take the credit out of the link, and a text that is only a credit is never a headline
(app/analysis/preprocessing.py, is_photo_credit). This re-reads the stored link html of older rows the same way.

Almost every such row held nothing but the credit, so there is nothing to rewrite it to; what to do with those is
for the person to decide, and this only lists them (read only, whatever the flags). A row whose link held a headline
besides the credit is listed with the headline it would be rewritten to.

    python scripts/clean_photo_credits.py              what it would change (the live database, read only)
    python scripts/clean_photo_credits.py --db PATH    the same on another copy
    python scripts/clean_photo_credits.py --all        every row, not ten examples per outlet"""
import argparse
import collections
import os
import sqlite3
import sys

from bs4 import BeautifulSoup as Soup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.analysis.preprocessing import extract_text, is_photo_credit  # noqa: E402
from app.scraper import without  # noqa: E402
from app.scrapers import abc, christiansciencemonitor, cnn, nbc  # noqa: E402
from app.utils import Config, Constants  # noqa: E402

# The credit's element on each front page, by what marks it in the stored html. Matched by the html, not the outlet:
# a few NBC rows sit under articles Drudge Report linked first (an article belongs to whoever linked its url first).
# Bloomberg's front page is no longer read (it answers with a captcha since Oct 11), so its selector lives only here.
PARTS = {'image-credit': nbc.PHOTO_PARTS, 'item-media-wrapper': cnn.PHOTO_PARTS, 'prism-indicator': abc.PHOTO_PARTS,
         'data-field="credit"': christiansciencemonitor.PHOTO_PARTS,
         'lazy-image-caption': '[data-component="lazy-image-caption"]'}


def changes(con: sqlite3.Connection):
    """(headline id, outlet, old title, new title or None when the link held only a credit) for every stored headline
    whose link html has a photo credit in it, or whose text is only a credit"""
    where = ' or '.join('h.raw like ?' for _ in PARTS)
    rows = con.execute(f"""select h.id, ag.name, h.title, h.raw from headline h join article a on a.id = h.article_id
        join agency ag on ag.id = a.agency_id where {where} or h.title like '%/%' or h.title like '% via %'""",
                       [f'%{m}%' for m in PARTS]).fetchall()
    for hid, agency, title, raw in rows:
        old = ' '.join(title.split())
        marks = [sel for mark, sel in PARTS.items() if mark in (raw or '')]
        if not marks:
            if is_photo_credit(old):
                yield hid, agency, old, None
            continue
        new = ' '.join(extract_text(without(Soup(raw, 'html.parser'), ', '.join(marks))).split())
        if len(new.split()) < Constants.Thresholds.min_headline_words or is_photo_credit(new):
            yield hid, agency, old, None
        elif new != old:
            yield hid, agency, old, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=Config.db_file_path)
    ap.add_argument('--all', action='store_true', help='list every row, not ten per outlet')
    args = ap.parse_args()
    con = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
    found = list(changes(con))
    credits = [f for f in found if f[3] is None]
    rewrites = [f for f in found if f[3] is not None]

    shown = collections.Counter()
    for hid, agency, old, new in found:
        shown[agency, new is None] += 1
        if args.all or shown[agency, new is None] <= 10:
            print(f'{agency} {hid}: {old!r}\n    -> ' + ('only a credit' if new is None else repr(new)))

    ids = {f[0] for f in credits}
    by_article = collections.defaultdict(list)  # headline.article_id has no index: one pass instead of subqueries
    for hid, aid in con.execute('select id, article_id from headline'):
        by_article[aid].append(hid)
    article = {hid: aid for aid, hids in by_article.items() for hid in hids if hid in ids}
    first = sum(min(by_article[aid]) == hid for hid, aid in article.items())
    alone = sum(all(h in ids for h in by_article[aid]) for aid in set(article.values()))
    in_stories = sum(hid in ids for hid, in con.execute('select headline_id from story_headline'))

    print()
    for agency, n in collections.Counter(f[1] for f in credits).most_common():
        print(f'{n:5d}  {agency}: only a credit')
    for agency, n in collections.Counter(f[1] for f in rewrites).most_common():
        print(f'{n:5d}  {agency}: a headline with a credit in it, to rewrite')
    print(f'{len(credits)} headlines are only a photo credit: {first} are their article\'s first headline, '
          f'{alone} articles have no other headline, {in_stories} are in a story')
    print(f'{len(rewrites)} headlines would be rewritten')
    print('nothing changed: this script only reads')


if __name__ == '__main__':
    main()
