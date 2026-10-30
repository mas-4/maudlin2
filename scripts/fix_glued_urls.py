"""Repair article addresses the scrapers glued together wrong (Oct 30, the person: "Sometimes our urls to outside sites
404"; "i think guardian fucks up a lot"). Front-page links were joined to the page's address as text, so
theguardian.com/us + /world/... became /us/world/... (a 404), France24 gave /en/en/..., and RFE/RL and Quillette a
double slash. Scraper.clean_href now resolves links as a browser does; this fixes the rows already stored.

An article whose right address is already stored (the outlet linked it both ways) keeps its row, and the misjoined
row's headlines move to it; the misjoined row is left behind with no headlines.

    fix_glued_urls.py           dry run: counts only
    fix_glued_urls.py --apply   writes (run while the hourly run is not going)"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app.utils.config import Config  # noqa: E402

GLUED = [  # (wrong prefix, right prefix)
    ('https://www.theguardian.com/us/', 'https://www.theguardian.com/'),
    ('https://www.france24.com/en/en/', 'https://www.france24.com/en/'),
    ('https://www.rferl.org//', 'https://www.rferl.org/'),
    ('https://quillette.com//', 'https://quillette.com/'),
]


def fixes(db: sqlite3.Connection) -> list[tuple[int, str, str]]:
    out = []
    for wrong, right in GLUED:
        for i, url in db.execute('select id, url from article where substr(url, 1, ?) = ?', (len(wrong), wrong)):
            out.append((i, url, right + url[len(wrong):]))
    return out


def main(apply: bool):
    db = sqlite3.connect(Config.db_file_path, timeout=60)
    todo = fixes(db)
    renamed = merged = 0
    with db:
        for i, _url, fixed in todo:
            have = db.execute('select id from article where url = ? and id != ?', (fixed, i)).fetchone()
            if have:
                merged += 1
                if apply:
                    db.execute('update headline set article_id = ? where article_id = ?', (have[0], i))
            else:
                renamed += 1
                if apply:
                    db.execute('update article set url = ? where id = ?', (fixed, i))
        if not apply:
            db.rollback()
    print(f"{'Fixed' if apply else 'Would fix'} {len(todo)} addresses: {renamed} renamed, {merged} merged into the "
          f"article already stored under the right address")


if __name__ == '__main__':
    main('--apply' in sys.argv[1:])
