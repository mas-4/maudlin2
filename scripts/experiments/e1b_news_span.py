"""E1b The news of the claims' own time (docs/filing-experiments.md; the person: "have we tried back de-newsing old
claims?"). E1 took out the main directions of the latest 6,000 headlines, but those are one snapshot of today's front
pages (a headline's last_accessed moves while it stays up: all 6,000 were from the last three minutes), while the
person's claims go back to July. Here the directions come from headlines spread over the claims' whole span instead,
an even number from each day they were first seen; the same two signals, against E1's."""
import sqlite3
import sys

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
import numpy as np  # noqa: E402

import e1_news  # noqa: E402  (its headlines, notes, claims and signals for the latest snapshot)
from app.utils import Config  # noqa: E402

PER_DAY = 120


def span_titles(first: str) -> list[str]:
    con = sqlite3.connect(f'file:{Config.connection_string.removeprefix("sqlite:///")}?mode=ro', uri=True)
    days = [r[0] for r in con.execute("SELECT DISTINCT date(first_accessed) FROM headline WHERE first_accessed >= ? "
                                      "ORDER BY 1", (first,))]
    out = []
    for d in days:
        out += [r[0] for r in con.execute("SELECT DISTINCT title FROM headline WHERE title IS NOT NULL AND "
                                          "date(first_accessed) = ? ORDER BY random() LIMIT ?", (d, PER_DAY))]
    return out


if __name__ == '__main__':
    data = e1_news.data
    dates = sorted(c.get('date') for e in data['entries'].values() for c in e['claims'] if c.get('date'))
    titles = span_titles(dates[0])
    print(f'{len(titles)} headlines from {dates[0]} on', flush=True)
    snap = (e1_news.Vt, e1_news.mu)
    H = e1_news.vec(titles)
    mu = H.mean(0)
    _, _, Vt = np.linalg.svd(H - mu, full_matrices=False)
    for k in (40, 80):
        e1_news.Vt, e1_news.mu = snap  # the latest snapshot's, for comparison
        note, near = e1_news.signals(k)
        harness.evaluate(data, {'note minus news': note, 'nearest minus news': near}, label=f'E1 today\'s front pages, {k} out')
        e1_news.Vt, e1_news.mu = Vt, mu
        note, near = e1_news.signals(k)
        harness.evaluate(data, {'note minus news': note, 'nearest minus news': near}, label=f'E1b the claims\' whole span, {k} out')
    print('DONE', flush=True)
