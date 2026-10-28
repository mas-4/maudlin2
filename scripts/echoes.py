"""Historical echoes (Oct 28): today's motifs told in 1896 newspapers, for the site's "Older than you think" page.

The person (Oct 28): the historical echoes are "one of the things I am *most* eager to see live". The 1896 claims come
from Rip Van Winkle (A2, papers/rip-van-winkle.md): 520 political articles of 1896 (American Stories, from Chronicling
America), their claims filed to a copy of today's index. An echo is one of those filings, sure (fit at the sure line
or above), to a motif the site shows. Every echo the site shows is one the person approved: approving it is also
Rip Van Winkle's spot-check of its sure filings (hypothesis 3), never run till now.

    python scripts/echoes.py propose          add candidates (one per motif, the surest; reprinted ones first)
    python scripts/echoes.py slate [-n 10]    the next candidates, with the article around the quote, for reading
    python scripts/echoes.py decide ID approve --quote "cleaned quote" [--why ...] [--by person|claude]
    python scripts/echoes.py decide ID reject --why "..."
    python scripts/echoes.py decide ID hold --why "..."     for the person: near a slur or trope, or a close call
    python scripts/echoes.py list [--status approved]

Kept in archives/archives.sqlite, table echoes. The A2 run's own new motifs (M879 and up) carry ids today's index
reused for other motifs, so they are never joined by id; every other id is checked by name against today's index."""
import argparse
import json
import os
import re
import sys
from datetime import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app.analysis.echoes import connect  # noqa: E402
from app.utils import Config  # noqa: E402

STATE = os.path.join(Config.data, 'motifs', 'experiments', 'a2_newspapers.json')
RUN = 'A2:file:2026-10-16T11:48:14'  # Rip Van Winkle's filing of the 1896 claims to today's index
FIRST_NEW = 879  # the run's own new motifs start here; today's index reused these ids for others
QUOTE_WORDS = (10, 90)  # a quote short enough to read on a card, long enough to say something



def live_motifs() -> dict:
    """Today's public motifs, by id, with merged ones followed to where they went"""
    from app.analysis import motif_index as mi
    index = mi.load()
    entries = index['entries']
    out = {}
    for mid, e in entries.items():
        target = e
        seen = set()
        while target.get('merged_into') and target['merged_into'] in entries and target['id'] not in seen:
            seen.add(target['id'])
            target = entries[target['merged_into']]
        if mi.public(target):
            out[mid] = target
    return out


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text or ''))


def propose() -> int:
    """One candidate per public motif: its sure 1896 filing told in the most papers, then the surest"""
    live = live_motifs()
    with open(STATE, encoding='utf-8') as f:
        state = json.load(f)
    quotes = {(doc, c['claim']): c['quote'] for doc, cs in state['claims'].items() for c in cs}
    retold = state.get('retold', {})
    con = connect(write=True)
    rows = con.execute("""select f.claim, f.motif, f.fit, c.text, c.document, d.date, d.place, d.source, d.url, d.title
        from filings f join claims c on c.id = f.claim join documents d on d.corpus = c.corpus and d.id = c.document
        where f.run = ? and f.sure = 1""", (RUN,)).fetchall()
    best = {}
    for r in rows:
        mid = r['motif']
        if int(mid[1:]) >= FIRST_NEW or mid not in live:
            continue
        e = live[mid]  # ids under FIRST_NEW were copied from the real index: the same motif, renamed or not
        quote = quotes.get((r['document'], r['text']), '')
        if not QUOTE_WORDS[0] <= words(quote) <= QUOTE_WORDS[1]:
            continue
        cand = {'motif': e['id'], 'motif_name': e['name'], 'claim': r['claim'], 'claim_text': r['text'],
                'quote': quote, 'headline': r['title'], 'paper': r['source'], 'place': r['place'], 'date': r['date'],
                'url': r['url'], 'fit': r['fit'], 'retold': retold.get(r['text'], 1)}
        key = e['id']
        if key not in best or (cand['retold'], cand['fit']) > (best[key]['retold'], best[key]['fit']):
            best[key] = cand
    told = {mid: (e.get('told') or {}).get('events', 0) for mid, e in live.items()}
    added = 0
    now = dt.now().isoformat(timespec='seconds')
    for cand in sorted(best.values(), key=lambda c: (-told.get(c['motif'], 0), -c['retold'], -c['fit'])):
        cur = con.execute('insert or ignore into echoes (motif, motif_name, claim, run, claim_text, quote, headline, '
                          'paper, place, date, url, fit, retold, proposed_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (cand['motif'], cand['motif_name'], cand['claim'], RUN, cand['claim_text'], cand['quote'],
                           cand['headline'], cand['paper'], cand['place'], cand['date'], cand['url'], cand['fit'],
                           cand['retold'], now))
        added += cur.rowcount
    con.commit()
    print(f'{added} new candidates ({len(best)} motifs have a sure 1896 telling with a readable quote)')
    return added


def around(con, row, width: int = 1100) -> str:
    """The article around the quote, for reading it in context"""
    doc = con.execute('select c.document, c.corpus from claims c where c.id = ?', (row['claim'],)).fetchone()
    text = con.execute('select text from documents where corpus = ? and id = ?', (doc['corpus'], doc['document'])).fetchone()
    text = ' '.join((text['text'] if text else '').split())
    probe = ' '.join((row['quote'] or '').split())[:40]
    at = text.find(probe) if probe else -1
    if at < 0:
        return text[:width]
    start = max(0, at - width // 2)
    return ('…' if start else '') + text[start:start + width] + '…'


def slate(n: int):
    con = connect(write=True)  # creates the table on a first run
    rows = con.execute("select * from echoes where status = 'proposed' order by id limit ?", (n,)).fetchall()
    from app.analysis import motif_index as mi
    entries = mi.load()['entries']
    for r in rows:
        e = entries.get(r['motif'], {})
        print(f"\n#{r['id']} {r['motif']} {r['motif_name']}  (fit {r['fit']:.2f}, in {r['retold']} paper(s))")
        print(f"  motif: {mi.public_note(e) if e else ''}")
        print(f"  {r['date']}, {r['paper']}, {r['place']}\n  {r['url']}")
        print(f"  headline: {r['headline']}\n  claim: {r['claim_text']}\n  quote: {r['quote']}")
        print(f"  around: {around(con, r)}")
    left = con.execute("select count(*) from echoes where status = 'proposed'").fetchone()[0]
    print(f'\n{len(rows)} shown, {left} proposed in all')


def decide(echo_id: int, verdict: str, quote: str | None, why: str | None, by: str = 'claude'):
    """Record a verdict, and who made it: the person, or Claude reading the whole article (Oct 28, the person: "a
    combination, sometimes human sometimes opus 5.5 with extra attention which the human has found effective")"""
    con = connect(write=True)
    status = {'approve': 'approved', 'reject': 'rejected', 'hold': 'held'}[verdict]
    cur = con.execute('update echoes set status = ?, quote_clean = coalesce(?, quote_clean), why = ?, decided_at = ?, '
                      'reviewer = ? where id = ?',
                      (status, quote, why, dt.now().isoformat(timespec='seconds'), by, echo_id))
    con.commit()
    print(f'#{echo_id}: {status}' if cur.rowcount else f'#{echo_id}: no such echo')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('propose')
    s = sub.add_parser('slate')
    s.add_argument('-n', type=int, default=10)
    d = sub.add_parser('decide')
    d.add_argument('id', type=int)
    d.add_argument('verdict', choices=['approve', 'reject', 'hold'])
    d.add_argument('--by', choices=['person', 'claude'], default='claude')
    d.add_argument('--quote')
    d.add_argument('--why')
    li = sub.add_parser('list')
    li.add_argument('--status', default='approved')
    a = p.parse_args()
    if a.cmd == 'propose':
        propose()
    elif a.cmd == 'slate':
        slate(a.n)
    elif a.cmd == 'decide':
        decide(a.id, a.verdict, a.quote, a.why, a.by)
    else:
        con = connect()
        for r in con.execute('select id, motif_name, date, paper, status from echoes where status = ?', (a.status,)):
            print(dict(r))
