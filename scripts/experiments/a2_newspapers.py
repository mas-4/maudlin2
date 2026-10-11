"""A2 our method across time: the 1896 newspapers (Oct 11; planned Oct 10, the person: "I want to run A experiments").
American Stories (Dell et al. 2023, CC BY 4.0; Hugging Face dell-research-harvard/AmericanStories): Chronicling
America's front pages and inside pages, laid out into articles and read by OCR, the 1896 election year. Run through
our pipeline as it is, against a copy of today's motif index, never our database, check queue or index:
- does our filing hold up on text it has never seen, 130 years off and through OCR noise? The person spot-checks the
  filings the confidence model calls sure (~50), each linked to its page scan at the Library of Congress;
- controls first (Jesse Waites, "I pointed AI at 400 years of archives": prove the search finds what you know is
  there): 1896 is the "Crime of '73" (the silver demonetization told as a bankers' plot), the Cross of Gold, the
  Rothschilds and "British gold"; our money and banker-conspiracy motifs must turn up for those;
- what shapes it finds that we don't have (the proposer), the interesting part. Not a test of which motifs are "real"
  (the person, Oct 10: recurrence over time is not the test; old tellings are lineage).

Stages, each resumable, the GPU ones under the lease:
    a2_newspapers.py extract     the political articles, from the 5.9 GB archive into the archives' database (CPU)
    a2_newspapers.py sample      the controls and a sample of the rest
    a2_newspapers.py claims      Gemma 26B reads each for the claims it tells, each with its quote, kept only if the
                                 quote is in the article and supports it, as the shows' claims are (GPU)
    a2_newspapers.py file        which claims are retold (versions in two papers or more, as on two shows), then the
                                 filing machinery on the index copy, every kept claim (GPU)
    a2_newspapers.py record      what A2 has so far into that database: the sample, claims, filings
    a2_newspapers.py report      the numbers, and the spot-check list"""
import json
import os
import random
import re
import sys
import tarfile
import time

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.utils import Config  # noqa: E402

DATA = os.path.join(Config.data, 'archives', 'american_stories')
ARCHIVE = os.path.join(DATA, 'faro_1896.tar.gz')
WORK = os.path.join(DATA, 'a2_1896')  # everything A2 makes: never the production data folder
OUT = os.path.join(harness.EXP, 'a2_newspapers.json')
MIN_CHARS = 600  # shorter pieces are mostly briefs, ads and notices
# The campaign's words, to find political articles among the ads, serials and market reports
POLITICS = re.compile(r'\b(silver|gold standard|free coinage|bimetal\w*|Bryan|McKinley|Hanna|tariff|Wall street|'
                      r'Rothschild\w*|banker\w*|money power|plutocra\w*|populist\w*|gold ?bug\w*|trusts?|monopol\w*|'
                      r'conspira\w*|Lombard street|British gold|Shylock\w*|syndicate|election|Democrat\w*|'
                      r'Republican\w*|campaign|sixteen to one|16 to 1)\b', re.I)
CONTROLS = {  # what 1896 is known to tell: these must reach our money and banker-conspiracy motifs
    "Crime of '73": re.compile(r"crime of (18)?['’]?73|crime of 1873|demoneti[sz]\w*", re.I),
    'Cross of Gold': re.compile(r'cross of gold|crown of thorns', re.I),
    'Rothschilds and British gold': re.compile(r'Rothschild\w*|British gold|Lombard street', re.I),
}


def page_url(lccn: str, date: str, edition: str, page: str) -> str:
    """The page at the Library of Congress (Chronicling America's address; it forwards to loc.gov)"""
    ed = int(re.sub(r'\D', '', edition) or 1)
    return f'https://chroniclingamerica.loc.gov/lccn/{lccn}/{date}/ed-{ed}/seq-{page}/'


def extract():
    """Every article of MIN_CHARS or more with POLITICS in it, straight into the archives' database (word-searchable),
    no file between (the person, Oct 11: no 1 GB JSON files)"""
    import archive_db as db
    seen = kept = pages = 0
    started = time.time()
    batch = []
    with tarfile.open(ARCHIVE, 'r:gz') as t:
        for m in t:
            if not m.isfile() or not m.name.endswith('.json'):
                continue
            pages += 1
            try:
                d = json.load(t.extractfile(m))
            except ValueError:
                continue
            name = os.path.basename(m.name)
            page = (re.search(r'_p(\d+)_', name) or [None, '1'])[1]
            paper, ed = d.get('lccn', {}), d.get('edition', {})
            for a in d.get('full articles', []):
                seen += 1
                text = ' '.join((a.get('article') or '').replace('-\n', '').split())
                if len(text) < MIN_CHARS or len(POLITICS.findall(text)) < 2:
                    continue
                kept += 1
                batch.append({'id': a.get('id'), 'title': ' '.join((a.get('headline') or '').split()), 'text': text,
                              'source': paper.get('title', ''), 'place': paper.get('state', ''), 'date': ed.get('date', ''),
                              'url': page_url(paper.get('lccn', ''), ed.get('date', ''), ed.get('edition', 'ed-01'), page),
                              'controls': [c for c, rx in CONTROLS.items() if rx.search(text)]})
            if len(batch) >= 5000:
                db.documents(CORPUS, batch)
                batch = []
            if pages % 20000 == 0:
                print(f'{pages} pages, {seen} articles, {kept} political, {(time.time() - started) / 60:.0f} min', flush=True)
    db.documents(CORPUS, batch)
    db.index_text()
    print(f'extract: {pages} pages, {seen} articles, {kept} political, into {db.DB}', flush=True)


def political() -> list[dict]:
    """The year's political articles from the archives' database"""
    import archive_db as db
    con = db.connect()
    return [{'id': i, 'headline': t, 'text': x, 'paper': src, 'state': pl, 'date': d, 'url': u,
             'controls': json.loads(meta or '{}').get('controls', [])}
            for i, t, x, src, pl, d, u, meta in con.execute(
                'select id, title, text, source, place, date, url, meta from documents where corpus = ?', (CORPUS,))]


N_CONTROL = 40  # articles for each control
N_SAMPLE = 400  # and of the rest, spread over the year
SOURCE = 'narrative'  # our closest source: what people retell (the confidence model knows it)
CLAIMS_PROMPT = """This is an article from {paper}, {date}, read by OCR from a newspaper page scan (expect errors, \
run-together columns, stray words).

{headline}
{text}

List the claims about politics and public life it tells or argues: what it says is true, why it says things happen, \
what it says someone is like, stories it passes on. Claims the writer asserts, not ones quoted only to knock down. Not \
ads, market prices, notices or the paper's own business. At most six; none if it tells none. For each:
claim: in one plain sentence of your own, in the present tense, as a reader would retell it (no "the article says")
quote: the words in the article that tell it, copied exactly as printed above, OCR errors and all (one to three \
sentences)"""
CLAIMS_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "maxItems": 6, "items": {
    "type": "object", "properties": {"claim": {"type": "string", "maxLength": 300}, "quote": {"type": "string", "maxLength": 600}},
    "required": ["claim", "quote"]}}}, "required": ["claims"]}
# As the shows' claims are kept (app/analysis/show_claims.py): the quote must be in the article and support the claim.
# OCR garbles words, and the model may mend them when it copies, so the share of a quote's four-word runs that must be
# found is lower than the transcripts' (focus_group.FOUND, 0.6)
FOUND = 0.4
RETOLD = 2  # papers: a claim is retold once versions of it are in this many (the shows' MIN_SHOWS)
CHUNK = 6000  # characters of an article read (a long one: its start)


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


def sample():
    """Each control's articles (N_CONTROL, spread over the year), then N_SAMPLE of the rest, a few a week"""
    arts = political()
    rnd = random.Random(2)
    picked = {}
    for c in CONTROLS:
        has = [a for a in arts if c in a['controls']]
        rnd.shuffle(has)
        for a in sorted(has[:N_CONTROL], key=lambda a: a['date']):
            picked.setdefault(a['id'], a)
    rest = [a for a in arts if not a['controls'] and a['id'] not in picked]
    rnd.shuffle(rest)
    for a in rest[:N_SAMPLE]:
        picked[a['id']] = a
    state = saved()
    state['articles'] = picked
    state['counts'] = {'political': len(arts), **{c: sum(c in a['controls'] for a in arts) for c in CONTROLS}}
    save(state)
    print(f"sample: {len(picked)} articles ({state['counts']})", flush=True)


def claims():
    """Gemma 26B's claims for each sampled article, PARALLEL at once, each kept only if its quote is in the article and
    supports it (the shows' checks); the dropped ones kept too, with why"""
    from app.analysis import focus_group as fg
    from app.analysis import llm
    from app.analysis import motif_signals as ms
    fg.FOUND = FOUND
    state = saved()
    got = state.setdefault('claims', {})
    dropped = state.setdefault('dropped', {})
    todo = [a for k, a in state['articles'].items() if k not in got]

    def read(a):
        r = llm.complete_json(CLAIMS_PROMPT.format(paper=a['paper'], date=a['date'], headline=a['headline'],
                                                   text=a['text'][:CHUNK]), CLAIMS_SCHEMA, max_tokens=1200,
                              model=ms.JUDGE_MODEL)
        if r is None:
            return None
        found = [{'claim': ' '.join(c.get('claim', '').split()), 'quote': c.get('quote', '').strip()}
                 for c in r.get('claims', []) if sum(ch.isalpha() for ch in c.get('claim', '')) >= 12]
        kept, out = fg.checked(found, a['text'][:CHUNK])
        for c in list(kept):
            if fg.supported(c['claim'], c['quote'], who=f"A newspaper ({a['paper']}, {a['date']})", noun='paper') is False:
                kept.remove(c)
                out.append(dict(c, why="the quote doesn't support the claim"))
        return kept, out
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        answers = llm.parallel(read, part)
        for a, r in zip(part, answers):
            if r is not None:
                got[a['id']], dropped[a['id']] = r
        save(state)
        if all(r is None for r in answers):  # Ollama down (restarted on Oct 11 mid-run: the stage raced through every
            sys.exit('claims: no answer for a whole batch; Ollama down? stopping to try again')  # article and "finished")
        n, d = sum(map(len, got.values())), sum(map(len, dropped.values()))
        print(f"claims: {len(got)}/{len(state['articles'])} articles, {n} claims kept, {d} dropped", flush=True)


def retold(state: dict) -> dict[str, int]:
    """Claim -> how many papers tell a version of it (versions grouped as the posts and shows are: app.narratives)"""
    from app.narratives import groups
    rows = [(c['claim'], state['articles'][k]['paper']) for k, cs in state['claims'].items() for c in cs]
    out = {c: 1 for c, _ in rows}
    for g in groups([{'text': c} for c, _ in rows]):
        papers = len({rows[i][1] for i in g})
        for i in g:
            out[rows[i][0]] = max(out[rows[i][0]], papers)
    return out


def sandbox():
    """Every file the filing machinery reads and writes, pointed at copies in WORK (copied once from production, so
    its caches start warm): the index, the signals' caches, the logs, the shortlist's and confidence model's weights.
    Production's files are only read, once, here"""
    import shutil
    from app.analysis import filing_confidence as fc
    from app.analysis import motif_index as mi
    from app.analysis import motif_proposals as mp
    from app.analysis import motif_retriever as mr
    from app.analysis import motif_signals as ms
    from app.utils.store import write_json
    box = os.path.join(WORK, 'sandbox')
    os.makedirs(os.path.join(box, 'motifs'), exist_ok=True)
    moves = [(mi, 'INDEX'), (mi, 'METRICS'), (mi, 'FILING_LOG'), (ms, 'SHAPES'), (ms, 'RERANKS'), (ms, 'JUDGED'),
             (ms, 'ELEMENTS'), (ms, 'LAYERED'), (ms, 'NEWS'), (fc, 'MODEL'), (fc, 'HISTORY'), (fc, 'ALTERNATIVES'),
             (mr, 'WEIGHTS'), (mr, 'LEARNED'), (mp, 'PROPOSALS'), (mp, 'RUNS')]
    for mod, name in moves:
        old = getattr(mod, name)
        new = os.path.join(box, os.path.relpath(old, Config.data))
        os.makedirs(os.path.dirname(new), exist_ok=True)
        if not os.path.exists(new) and os.path.exists(old):
            shutil.copy2(old, new)
        setattr(mod, name, new)
    mi.save = lambda index: write_json(mi.INDEX, index, indent=1)  # no versions into production's curation database
    return box


def file():
    """Our filing on the index copy: each claim shortlisted, picked or given a new motif, then scored by the
    confidence model (its fit: the chance the person keeps it)"""
    sandbox()
    from app.analysis import filing_confidence as fc
    from app.analysis import motif_index as mi
    from app.utils.store import read_json
    state = saved()
    arts = state['articles']
    state['retold'] = retold(state)
    save(state)
    todo = [{'claim': c['claim'], 'source': SOURCE, 'ref': k, 'date': arts[k]['date']}
            for k, cs in state['claims'].items() for c in cs]
    print(f'file: {len(todo)} claims', flush=True)
    mi.file_claims(todo, limit=len(todo))
    index = mi.load()
    m = read_json(fc.MODEL, None)
    mine = {mi.key(c['claim']) for c in todo}
    skip = {(k, eid) for k, ids in index['claims'].items() if k not in mine for eid in ids}  # ours already have fits
    fits = fc.score(index, m, skip=skip)
    state['filed'] = {k: [{'motif': eid, 'name': index['entries'][eid]['name'], 'fit': fits.get((k, eid))}
                          for eid in index['claims'].get(k, [])] for k in mine}
    state['new_motifs'] = {e['id']: {'name': e['name'], 'claims': [c['claim'] for c in e['claims']]}
                           for e in mi.live(index) if e.get('first_seen') == time.strftime('%Y-%m-%d')
                           and all(mi.key(c['claim']) in mine for c in e['claims'])}
    state['sure_at'] = (m or {}).get('test', {}).get('sure_at')
    save(state)
    print(f"file: {sum(1 for v in state['filed'].values() if v)} of {len(mine)} claims filed, "
          f"{len(state['new_motifs'])} new motifs", flush=True)


CORPUS = 'american_stories_1896'


def record():
    """What A2 has so far into the archives' database (scripts/experiments/archive_db.py), to revisit and query:
    the sampled articles, their claims, and once filed, the filings with their fits and the motifs as they stood.
    Safe to run again: each stage keeps one run id"""
    import archive_db as db
    from app.analysis import motif_signals as ms
    state = saved()
    runs = state.setdefault('runs', {})
    arts = state.get('articles', {})
    db.documents(CORPUS, [{'id': k, 'title': a['headline'], 'date': a['date'], 'place': a['state'],
                           'source': a['paper'], 'url': a['url'], 'text': a['text'], 'controls': a['controls']}
                          for k, a in arts.items()])
    ids = {}
    if state.get('claims'):
        runs.setdefault('claims', db.run('A2', 'claims', f'Gemma reads each article for its claims ({ms.JUDGE_MODEL})'))
        for k, cs in state['claims'].items():
            texts = [c['claim'] for c in cs]
            for c, i in zip(texts, db.claims(CORPUS, k, texts, ms.JUDGE_MODEL, CLAIMS_PROMPT, runs['claims'])):
                ids[c] = i
    if state.get('filed'):
        sandbox()
        from app.analysis import motif_index as mi
        runs.setdefault('file', db.run('A2', 'file', 'our filing on a copy of the motif index; fits by the '
                                                      f"confidence model, sure at {state.get('sure_at')}"))
        index = mi.load()
        db.motifs(runs['file'], mi.live(index), set(state.get('new_motifs', {})))
        by_key = {mi.key(c): i for c, i in ids.items()}
        sure = state.get('sure_at') or 1
        db.filings(runs['file'], [(by_key[k], f['motif'], f['fit'], f['fit'] is not None and f['fit'] >= sure)
                                  for k, fs in state['filed'].items() if k in by_key for f in fs])
    save(state)
    print(f"record: {len(arts)} articles, {len(ids)} claims, {sum(len(v) for v in state.get('filed', {}).values())} "
          f"filings into {db.DB}", flush=True)


SPOT = 50  # sure filings for the person to check against the page scans


def report():
    """The numbers (claims kept and dropped, filed, sure, retold against one-off, the controls' motifs, new motifs),
    into the experiments' log; and the spot-check list: SPOT sure filings with their quote and page scan"""
    from collections import Counter
    import numpy as np
    sandbox()
    from app.analysis import motif_index as mi
    state = saved()
    arts, claims_of, filed = state['articles'], state.get('claims', {}), state.get('filed', {})
    sure = state.get('sure_at') or 0.8
    index = mi.load()
    rows = []  # (article id, claim, quote, motif, fit)
    for k, cs in claims_of.items():
        for c in cs:
            for f in filed.get(mi.key(c['claim']), []):
                rows.append((k, c['claim'], c['quote'], f['motif'], f['fit']))
    kept = sum(map(len, claims_of.values()))
    dropped = Counter(d['why'] for ds in state.get('dropped', {}).values() for d in ds)
    n_filed = sum(1 for k, cs in claims_of.items() for c in cs if filed.get(mi.key(c['claim'])))
    fits = [r[4] for r in rows if r[4] is not None]
    rt = state.get('retold', {})
    lines = [f"A2 1896 newspapers: {len(arts)} articles ({state['counts']['political']:,} political in the year), "
             f"{kept} claims kept, dropped {dict(dropped)}; {n_filed} filed in {len(rows)} filings; "
             f"{len(state.get('new_motifs', {}))} new motifs",
             f"  fits: {len(fits)} scored (in the person's motifs), median {np.median(fits):.2f}; sure (>= {sure}) "
             f"{sum(f >= sure for f in fits)} ({np.mean([f >= sure for f in fits]):.0%})" if fits else '  fits: none scored']
    for label, test in (('retold (2+ papers)', lambda c: rt.get(c, 1) >= RETOLD), ('one paper', lambda c: rt.get(c, 1) < RETOLD)):
        fs = [r[4] for r in rows if r[4] is not None and test(r[1])]
        if fs:
            lines.append(f'  {label}: {len(fs)} scored filings, median fit {np.median(fs):.2f}, sure {np.mean([f >= sure for f in fs]):.0%}')
    for control in CONTROLS:
        motifs = Counter(index['entries'][r[3]]['name'] for r in rows if control in arts[r[0]]['controls'] and r[3] in index['entries'])
        lines.append(f"  control {control}: " + ', '.join(f'{n} {k}' for n, k in ((k, v) for k, v in motifs.most_common(8))))
    lines.append('  new motifs: ' + '; '.join(f"{v['name']} ({len(v['claims'])})" for v in
                                               sorted(state.get('new_motifs', {}).values(), key=lambda v: -len(v['claims']))[:15]))
    for line in lines:
        print(line, flush=True)
        harness.note(line)
    pool = [r for r in rows if r[4] is not None and r[4] >= sure]
    picks = random.Random(5).sample(pool, min(SPOT, len(pool)))
    spot = [{'claim': c, 'quote': q, 'motif': index['entries'][m]['name'], 'note': index['entries'][m].get('note', ''),
             'fit': f, 'paper': arts[k]['paper'], 'date': arts[k]['date'], 'url': arts[k]['url'], 'headline': arts[k]['headline']}
            for k, c, q, m, f in picks]
    state['spot_check'] = spot
    save(state)
    print(f'report: {len(spot)} sure filings kept for the spot-check (state["spot_check"])', flush=True)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else 'extract'
    {'extract': extract, 'sample': sample, 'claims': claims, 'file': file, 'record': record,
     'report': report}[stage]()
    print('DONE', flush=True)


if __name__ == '__main__':
    random.seed(2)
    main()
