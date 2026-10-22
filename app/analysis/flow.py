"""How news stories flow into retellings, over time (Oct 12, the person: "some kind of map view that shows how stories
end up flowing into retellings temporally"). Since Oct 12 a filing keeps the news story its claim was told about
(motif_index's story ids: a posts group's tie by the model or by the links its posts share, a fact-check's by its
story card), so a story's life in the news and the motifs it was later told as are a join:

    stories   each story with a filing: its label, when it was first and last in the news (the site database's story
              table), and its filings, oldest first: the day, the motif, its genre, the source kind, the claim, whether
              the person has checked it, whether the motif is a watch list (plain reporting: the baseline), and the lag
              in days from the story's first day in the news to the filing
    motifs    every motif those filings are in, with its genre and how many stories fed it

Read only; the checker's 🌊 flow page draws it (scripts/checker/ui/src/pages/flow)."""
from collections import defaultdict
from datetime import datetime as dt

from app.analysis import motif_index as mi

SOURCE_KIND = {'narrative': 'posts', 'shows': 'shows', 'Focus Group': 'focus group'}  # anything else: a fact-check


def kind_of(source: str) -> str:
    return SOURCE_KIND.get(source, 'fact-check')


def story_rows(ids: set[int]) -> dict[int, dict]:
    """The stories' labels and days in the news, from the site database"""
    from app.models import Session, Story
    if not ids:
        return {}
    with Session() as s:
        return {sid: {'label': label, 'first': first.isoformat(timespec='minutes') if first else None,
                      'last': last.isoformat(timespec='minutes') if last else None}
                for sid, label, first, last in s.query(Story.id, Story.label, Story.first_seen, Story.last_seen)
                .filter(Story.id.in_(sorted(ids)))}


def flow(index: dict | None = None) -> dict:
    from app.analysis import stories as st
    index = index if index is not None else mi.load()
    merged = st.merges()
    watched = mi.watched(index)
    filings = defaultdict(list)
    for e in mi.live(index):
        for c in e['claims']:
            if c.get('story') is None:
                continue
            try:
                sid = int(c['story'])
            except (TypeError, ValueError):
                continue
            sid = merged.get(sid, sid)
            filings[sid].append({'date': c.get('date') or '', 'motif': e['id'], 'source': kind_of(c.get('source', '')),
                                 'claim': c['claim'], 'checked': c.get('checked') == 'yes', 'plain': e['id'] in watched,
                                 'tie': c.get('story_tie') or 'same event'})
    rows = story_rows(set(filings))
    out, fed = [], defaultdict(set)
    for sid, fs in filings.items():
        row = rows.get(sid)
        if not row:  # a story no longer in the database
            continue
        first = dt.fromisoformat(row['first']).date() if row['first'] else None
        for f in fs:
            day = dt.fromisoformat(f['date']).date() if f['date'] else None
            f['lag'] = (day - first).days if day and first else None
            fed[f['motif']].add(sid)
        fs.sort(key=lambda f: (f['date'], f['motif']))
        out.append({'id': sid, **row, 'filings': fs,
                    'motifs': len({f['motif'] for f in fs if not f['plain']})})
    out.sort(key=lambda s: s['first'] or '')
    entries = index['entries']
    motifs = {m: {'name': entries[m]['name'], 'genre': mi.person_genre(entries[m]) or mi.genre_of(entries[m]) or '',
                  'stories': len(ids), 'plain': m in watched}
              for m, ids in fed.items() if m in entries}
    lags = [f['lag'] for s in out for f in s['filings'] if f['lag'] is not None and not f['plain']]
    return {'stories': out, 'motifs': motifs, 'genres': mi.facet_values(index).get('genre', []),
            'filings': sum(len(s['filings']) for s in out), 'lags': lags,
            'made': dt.now().isoformat(timespec='seconds')}
