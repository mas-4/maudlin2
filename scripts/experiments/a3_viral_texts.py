"""A3 does one text file alike every time it's printed? (Oct 11.) Viral Texts (Cordell and Smith, Northeastern; the
ALH_data release: the 50,000 most reprinted passages of American newspapers 1836-61, each reprint with its paper, date
and page): every cluster is one piece, a poem, a speech, a news item, a political squib, reprinted across the country,
each copy with its own OCR errors, cuts and editors' changes. Our pipeline as A2 runs it (claims with their quotes
checked, then our filing on a copy of the motif index, all in A3's own folder), on several copies of each of a sample
of political clusters. If filing is consistent, copies of one piece land on the same motifs: within a cluster the
copies' motif sets should overlap far more than copies of different pieces do.

    a3_viral_texts.py load      every reprint into the archives' database, word-searchable (CPU)
    a3_viral_texts.py sample    political clusters with COPIES reprints or more, COPIES of each from different papers
    a3_viral_texts.py claims    Gemma reads each copy (GPU)
    a3_viral_texts.py file      our filing on the index copy (GPU)
    a3_viral_texts.py report    within-cluster agreement against between-cluster, into the log; then `record`"""
import csv
import json
import os
import random
import re
import sys
from collections import defaultdict

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import a2_newspapers as a2  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.utils import Config  # noqa: E402

DATA = os.path.join(Config.data, 'archives', 'viral_texts')
TSV = os.path.join(DATA, '1861-top50000.csv')
WORK = os.path.join(DATA, 'a3')
OUT = os.path.join(harness.EXP, 'a3_viral_texts.json')
CORPUS = 'viral_texts_1836_1861'
CLUSTERS = 60
COPIES = 4
MIN_CHARS = 400
POLITICS = re.compile(r'\b(slaver\w*|abolition\w*|Union|Congress|Senat\w*|President|Democrat\w*|Whig\w*|Republican\w*|'
                      r'Know[- ]Nothing\w*|Kansas|Nebraska|Missouri|tariff|election|vote\w*|government|party|'
                      r'politic\w*|Constitution|disunion|secession|fugitive|Douglas|Buchanan|Lincoln|Fremont|Pierce)\b', re.I)


def rows() -> list[dict]:
    csv.field_size_limit(10 ** 8)
    with open(TSV, newline='') as f:
        out = []
        for r in csv.DictReader(f, delimiter='\t'):
            text = ' '.join(re.sub(r'<br/>', ' ', r.get('Text') or '').replace('- ', '').split())
            url = (r.get('URL') or '').split('/print/')[0] + '/'
            out.append({'cluster': r['ID'], 'reprints': int(r.get('Number_of_reprints') or 0), 'date': r.get('Date', ''),
                        'paper': r.get('Newspaper', ''), 'url': url, 'text': text,
                        'id': f"{r['ID']}:{r.get('#', '')}:{r.get('Date', '')}"})
    return out


def saved() -> dict:
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def save(state: dict):
    json.dump(state, open(OUT + '.tmp', 'w'))
    os.replace(OUT + '.tmp', OUT)


def load():
    import archive_db as db
    rs = rows()
    db.documents(CORPUS, [{'id': r['id'], 'title': f"cluster {r['cluster']}", 'date': r['date'], 'source': r['paper'],
                           'url': r['url'], 'text': r['text'], 'cluster': r['cluster'], 'reprints': r['reprints']} for r in rs])
    db.index_text()
    print(f'load: {len(rs)} reprints in {len({r["cluster"] for r in rs})} clusters into {db.DB}', flush=True)


def sample():
    by = defaultdict(list)
    for r in rows():
        if len(r['text']) >= MIN_CHARS:
            by[r['cluster']].append(r)
    rnd = random.Random(3)
    political = [c for c, rs in by.items() if len({r['paper'] for r in rs}) >= COPIES
                 and len(POLITICS.findall(max(rs, key=lambda r: len(r['text']))['text'])) >= 3]
    rnd.shuffle(political)
    picked = {}
    for c in political[:CLUSTERS]:
        seen, copies = set(), []
        for r in sorted(by[c], key=lambda r: rnd.random()):
            if r['paper'] not in seen:
                seen.add(r['paper'])
                copies.append(r)
            if len(copies) == COPIES:
                break
        for r in copies:
            picked[r['id']] = {'id': r['id'], 'headline': '', 'paper': r['paper'], 'date': r['date'], 'url': r['url'], 'text': r['text'],
                               'state': '', 'controls': [], 'cluster': c}
    state = saved()
    state['articles'] = picked
    state['clusters'] = len(political)
    save(state)
    print(f'sample: {len(picked)} copies of {min(CLUSTERS, len(political))} clusters ({len(political)} political with '
          f'{COPIES}+ papers)', flush=True)


def use_a2():
    """A2's claims and filing stages, pointed at A3's state and folder"""
    a2.OUT, a2.WORK, a2.CORPUS = OUT, WORK, CORPUS
    os.makedirs(WORK, exist_ok=True)


def claims():
    use_a2()
    a2.claims()


def file():
    use_a2()
    a2.file()


def record():
    use_a2()
    a2.record()


def report():
    """Within a cluster, how alike are the copies' motif sets (Jaccard), against copies of different clusters"""
    import numpy as np
    use_a2()
    a2.sandbox()
    from app.analysis import motif_index as mi
    state = saved()
    arts, filed = state['articles'], state.get('filed', {})
    motifs = {k: {f['motif'] for c in cs for f in filed.get(mi.key(c['claim']), [])} for k, cs in state.get('claims', {}).items()}
    motifs = {k: v for k, v in motifs.items() if v}
    by = defaultdict(list)
    for k in motifs:
        by[arts[k]['cluster']].append(k)

    def jac(a, b):
        return len(motifs[a] & motifs[b]) / len(motifs[a] | motifs[b])
    within = [jac(a, b) for ks in by.values() for i, a in enumerate(ks) for b in ks[i + 1:]]
    keys = list(motifs)
    if len(by) < 2:
        print(f'report: only {len(keys)} copies with filings; nothing to compare yet', flush=True)
        return
    rnd = random.Random(4)
    between = [jac(a, b) for a, b in (rnd.sample(keys, 2) for _ in range(3000)) if arts[a]['cluster'] != arts[b]['cluster']]
    shared = [len(set.intersection(*(motifs[k] for k in ks))) > 0 for ks in by.values() if len(ks) >= 2]
    line = (f"A3 Viral Texts: {len(motifs)} copies with filings in {len(by)} clusters; motif sets alike (Jaccard) within a "
            f"cluster {np.mean(within):.2f} against {np.mean(between):.2f} between clusters; a motif common to every copy "
            f"in {np.mean(shared):.0%} of clusters")
    print(line, flush=True)
    harness.note(line)


def main():
    {'load': load, 'sample': sample, 'claims': claims, 'file': file, 'record': record, 'report': report}[sys.argv[1]]()
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
