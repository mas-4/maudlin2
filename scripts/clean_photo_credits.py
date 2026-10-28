"""Photo credits stored as headlines (Oct 28): NBC News, CNN, ABC News and The Christian Science Monitor link each
story's photo on its own, with the photo's credit inside the link, so the link read as "Saul Loeb / AFP via Getty"
and was kept as a headline, often as its article's first. Bloomberg's front page did the same until it moved to its
feeds (Oct 11). The scrapers now take the credit out of the link, and a text that is only a credit is never a headline
(app/analysis/preprocessing.py, is_photo_credit). This re-reads the stored link html of older rows the same way.

Almost every such row held nothing but the credit, so there is nothing to rewrite it to. The person (Oct 28):
delete them. --apply deletes each credit-only headline, its story links, and any article left with no headline; a row
whose link held a headline besides the credit is rewritten to that headline. Back the database up first.

    python scripts/clean_photo_credits.py                      what it would change (the live database, read only)
    python scripts/clean_photo_credits.py --db PATH            the same on another copy
    python scripts/clean_photo_credits.py --all                every row, not ten examples per outlet
    python scripts/clean_photo_credits.py --db PATH --apply    change them"""
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


def apply(con: sqlite3.Connection, found: list) -> dict:
    """Delete the credit-only headlines (story links first) and the articles left with none; rewrite the rest. One
    transaction: all of it or none"""
    from app.analysis.preprocessing import preprocess
    ids = [f[0] for f in found if f[3] is None]
    con.execute('begin immediate')
    try:
        con.execute('create temp table gone (id integer primary key)')
        con.executemany('insert into gone values (?)', [(i,) for i in ids])
        arts = [a for a, in con.execute('select distinct article_id from headline where id in (select id from gone)')]
        links = con.execute('delete from story_headline where headline_id in (select id from gone)').rowcount
        heads = con.execute('delete from headline where id in (select id from gone)').rowcount
        con.execute('create temp table touched (id integer primary key)')
        con.executemany('insert into touched values (?)', [(a,) for a in arts])
        empty = con.execute('''delete from article where id in (select id from touched)
            and not exists (select 1 from headline h where h.article_id = article.id)''').rowcount
        rewrites = [(new, preprocess(new), hid) for hid, _, _, new in found if new is not None]
        con.executemany('update headline set title = ?, processed = ? where id = ?', rewrites)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {'headlines': heads, 'story links': links, 'articles': empty, 'rewritten': len(rewrites)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=Config.db_file_path)
    ap.add_argument('--all', action='store_true', help='list every row, not ten per outlet')
    ap.add_argument('--apply', action='store_true', help='delete the credits and rewrite the rest (back up first)')
    args = ap.parse_args()
    con = sqlite3.connect(f'file:{args.db}' + ('' if args.apply else '?mode=ro'), uri=True, timeout=120,
                          isolation_level=None)
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
    if not args.apply:
        print('nothing changed: run with --apply to delete them')
        return
    print('done:', apply(con, found))


if __name__ == '__main__':
    main()
