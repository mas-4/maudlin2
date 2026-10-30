"""F29 Hestia: each motif's centre, and how far its claims stray from it (Oct 30). The person: "average the claims under
each motif in embeddings space, maybe even tfidf them for a second metric, and see how things cluster", and "part of the
failure of past experiments was simply an insufficiently distinguished motif index". The shortlist already compares a
new claim with each motif's centre (motif_retriever.facts, mxbai); this looks at the centres themselves, on the index as
it stood at seven dates from Oct 9 (409 motifs) to Oct 30 (1,027).

    growth     nearest-centre recall at 1 / 12 / 40 and the margin (own centre less the nearest other), every version on
               its own claims, and the claims confirmed both on Oct 12 and today scored against both (paired)
    coverage   of the claims first confirmed after a cut date, how many had their motif (as it is today) already made
    spread     the margin as a sign of the person's take-outs against their keeps (AUC), each scored on the index
               version saved just before it
    map        pairwise centre likeness against related / rests-on links, shared groups, one genre, not-the-same (AUC);
               the centres clustered; the closest unjudged pairs and the claims farthest from their centres listed

Vectors come from the embedding cache only (mxbai, Qwen3-Embedding 8B, Snowflake Arctic 2, and mxbai with the news taken
out), plus TF-IDF: no model is asked and nothing uses the GPU. The paper is ~/maudlin-data/papers/hestia.md (hypotheses
written before the run).

    f29_hestia.py report [--quick]   everything above, saved to f29_hestia.sqlite and printed (--quick: a smoke
                                     test on 15 spread versions and 10 resamples, to f29_hestia.quick.sqlite)"""
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime as dt

import numpy as np
from scipy import sparse

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import curation_db as cdb  # noqa: E402
from app.analysis import local_models as lm  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402
from app.utils import Config  # noqa: E402

EXP = os.path.join(Config.data, 'motifs', 'experiments')
DB = os.path.join(EXP, 'f29_hestia.sqlite')
CACHE = os.path.join(Config.data, 'narratives', 'embeddings.sqlite')
CUTS = ['2026-10-09', '2026-10-12', '2026-10-16', '2026-10-20', '2026-10-24', '2026-10-28']
FIXED = '2026-10-12'  # the growth test: this version against the latest
EMBEDDERS = {'mxbai': lm.MXBAI, 'qwen3 8b': lm.QWEN3_EMBED, 'arctic2': lm.ARCTIC}
ARMS = ['mxbai', 'mxbai news out', 'qwen3 8b', 'arctic2', 'tfidf']
LISTS = 'qwen3 8b'  # the arm the person's lists are drawn from
KS = (1, 12, 40)
BOOTS = 200
QUICK = 0  # --quick: a smoke test on a few spread versions, few resamples, to its own file
TAKE_OUTS = {'unfile', 'not this motif', 'move'}


def parse(blob: bytes) -> dict:
    return json.loads(cdb._unpack(blob))


def lit(v):
    """A field as saved: some versions keep lists and dicts as their Python text"""
    if isinstance(v, str) and v[:1] in '[{':
        import ast
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    return v


class Index:
    """One saved version, kept small: live motifs, their confirmed claims (as text ids), every filing, links"""

    def __init__(self, idx: dict, at: str, texts: dict):
        ents = idx['entries']
        ents = list(ents.values()) if isinstance(ents, dict) else ents
        self.at = at
        self.merged = {e['id']: e['merged_into'] for e in ents if e.get('merged_into')}
        live = [e for e in ents if not e.get('merged_into')]
        self.ids = [e['id'] for e in live]
        self.done = {e['id'] for e in live if lit(e.get('done'))}
        self.genre = {e['id']: (lit(e.get('facets')) or {}).get('genre') for e in live
                      if isinstance(lit(e.get('facets')), dict)}
        self.groups = {e['id']: set(lit(e.get('groups')) or []) for e in live}
        self.parents = {e['id']: set(lit(e.get('parents')) or []) for e in live}
        self.related = {tuple(sorted(p)) for p in idx.get('related', []) if len(p) == 2}
        self.not_same = {tuple(sorted(p)) for p in idx.get('not_same', []) if len(p) == 2}
        self.confirmed, self.filed = {}, {}  # motif -> [text id]
        for e in live:
            cl = lit(e.get('claims')) or []
            ids = [texts.setdefault(c['claim'], len(texts)) for c in cl if isinstance(c, dict) and c.get('claim')]
            self.filed[e['id']] = list(dict.fromkeys(ids))
            self.confirmed[e['id']] = list(dict.fromkeys(
                texts[c['claim']] for c in cl if isinstance(c, dict) and c.get('claim') and c.get('checked') == 'yes'))
        self.truth = defaultdict(set)  # text id -> its done motifs (confirmed)
        for m in self.done:
            for t in self.confirmed[m]:
                self.truth[t].add(m)
        self.anywhere = defaultdict(set)  # text id -> every motif filing it
        for m, ts in self.filed.items():
            for t in ts:
                self.anywhere[t].add(m)


class Space:
    """One arm's centres over one Index: sums of the confirmed claims' unit vectors, so a claim can be left out"""

    def __init__(self, index: Index, X, have: np.ndarray):
        self.index = index
        self.mids = [m for m in index.ids if any(have[t] for t in index.confirmed[m])]
        self.row = {m: i for i, m in enumerate(self.mids)}
        r, c = [], []
        for i, m in enumerate(self.mids):
            for t in index.confirmed[m]:
                if have[t]:
                    r.append(i)
                    c.append(t)
        A = sparse.csr_matrix((np.ones(len(r)), (r, c)), shape=(len(self.mids), X.shape[0]))
        self.n = np.asarray(A.sum(1)).ravel()
        S = A @ X
        self.S = S.toarray() if sparse.issparse(S) else np.asarray(S)
        self.norm2 = (self.S ** 2).sum(1)
        self._mem = None

    def member(self, m: str) -> set:
        if self._mem is None:
            self._mem = {m: set(self.index.confirmed[m]) for m in self.mids}
        return self._mem[m]

    def likeness(self, q: np.ndarray, t: int | None) -> np.ndarray:
        """Cosine of q to every centre; a centre holding claim t has it left out (NaN when nothing is left)"""
        D = self.S @ q
        out = D / np.sqrt(np.maximum(self.norm2, 1e-12))
        if t is not None:
            for m in self.index.anywhere.get(t, ()):
                i = self.row.get(m)
                if i is not None and t in self.member(m):
                    if self.n[i] <= 1:
                        out[i] = np.nan
                    else:
                        out[i] = (D[i] - 1.0) / np.sqrt(max(self.norm2[i] - 2 * D[i] + 1.0, 1e-12))
        return out


def vectors(texts: dict) -> dict:
    """{arm: (matrix over text ids, have mask)} from the embedding cache and a TF-IDF fit over every text"""
    order = sorted(texts, key=texts.get)
    con = sqlite3.connect(f'file:{CACHE}?mode=ro', uri=True, timeout=120)
    out = {}
    for arm, model in EMBEDDERS.items():
        keys = [hashlib.sha1(f'{model}\n{t}'.encode()).hexdigest() for t in order]
        found = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in con.execute(
                f"SELECT key, v FROM vec WHERE key IN ({','.join('?' * len(chunk))})", chunk)})
        dim = len(next(iter(found.values())))
        X = np.zeros((len(order), dim), dtype=np.float64)
        have = np.zeros(len(order), dtype=bool)
        for i, k in enumerate(keys):
            if k in found:
                X[i] = found[k]
                have[i] = True
        out[arm] = (X, have)
        print(f'vectors {arm}: {have.sum()}/{len(order)} texts cached', flush=True)
    con.close()
    d = np.load(os.path.join(Config.data, 'motifs', 'news_directions.npz'))
    X, have = out['mxbai']
    W = ms.news_out(X, (d['center'], d['directions']))
    W[~have] = 0
    out['mxbai news out'] = (W, have)
    from sklearn.feature_extraction.text import TfidfVectorizer
    T = TfidfVectorizer(stop_words='english', sublinear_tf=True, ngram_range=(1, 2), min_df=2).fit_transform(order)
    T = sparse.csr_matrix(T, dtype=np.float64)
    have = np.asarray((T.multiply(T)).sum(1)).ravel() > 0
    out['tfidf'] = (T, have)
    print(f'vectors tfidf: {have.sum()}/{len(order)} texts with a word', flush=True)
    return out


def qvec(X, t: int) -> np.ndarray:
    return X[t].toarray().ravel() if sparse.issparse(X) else X[t]


def rank_claim(sim: np.ndarray, sp: Space, truth: set, own_all: set) -> dict | None:
    """Recall at KS, margin and the own motif's size for a claim, from its likeness to every centre"""
    have = {m for m in truth if m in sp.row and not np.isnan(sim[sp.row[m]])}
    if not have:
        return None
    s = np.where(np.isnan(sim), -np.inf, sim)
    order = np.argsort(-s)
    rank = {sp.mids[i]: r for r, i in enumerate(order)}
    rec = {k: sum(rank[m] < k for m in have) / len(have) for k in KS}
    own = max(s[sp.row[m]] for m in have)
    other = np.delete(s, [sp.row[m] for m in own_all if m in sp.row])
    margin = own - (other.max() if other.size else -1.0)
    size = max(sp.n[sp.row[m]] for m in have)
    return {**{f'r{k}': v for k, v in rec.items()}, 'margin': float(margin), 'own': float(own), 'size': int(size)}


def boot(vals: np.ndarray, seed: int = 0) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    if not len(vals):
        return float('nan'), float('nan'), float('nan')
    b = [vals[rng.integers(0, len(vals), len(vals))].mean() for _ in range(BOOTS)]
    return float(vals.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def auc(pos, neg) -> float:
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float('nan')
    allv = np.concatenate([pos, neg])
    from scipy.stats import rankdata
    r = rankdata(allv)
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def auc_boot(pos, neg, seed: int = 0) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    b = [auc(pos[rng.integers(0, len(pos), len(pos))], neg[rng.integers(0, len(neg), len(neg))]) for _ in range(BOOTS)]
    return auc(pos, neg), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def save(con, test, arm, version, metric, v, lo=None, hi=None, n=None):
    con.execute('insert into results values (?,?,?,?,?,?,?,?)', (test, arm, version, metric, v, lo, hi, n))


def report():
    os.makedirs(EXP, exist_ok=True)
    if os.path.exists(DB):
        os.replace(DB, DB + '.previous')
    out = sqlite3.connect(DB)
    out.executescript("""
        create table results (test text, arm text, version text, metric text, value real, lo real, hi real, n integer);
        create table claims (test text, arm text, version text, claim text, r1 real, r12 real, r40 real, margin real,
                             own real, size integer);
        create table spread (arm text, at text, kind text, motif text, claim text, margin real, own real);
        create table pairs (arm text, a text, b text, likeness real, link text);
        create table clusters (arm text, cut real, cluster integer, motif text, name text);
        create table far (arm text, motif text, name text, claim text, margin real, own real, nearest text);
        create table meta (key text, value text);""")
    out.execute('insert into meta values (?,?)', ('started', dt.now().isoformat(timespec='seconds')))
    texts: dict[str, int] = {}
    cu = sqlite3.connect(f'file:{cdb.DB}?mode=ro', uri=True)
    rows = cu.execute('select id, at from versions order by at').fetchall()

    # the seven versions
    picks = [(c, max((r for r in rows if r[1] < c), key=lambda r: r[1])) for c in CUTS] + [('latest', rows[-1])]
    V = {}
    for label, (vid, at) in picks:
        V[label] = Index(parse(cu.execute('select data from versions where id = ?', (vid,)).fetchone()[0]), at, texts)
        print(f'version {label} ({at}): {len(V[label].ids)} motifs, {len(V[label].truth)} confirmed claims', flush=True)
    names = {}
    latest_raw = parse(cu.execute('select data from versions where id = ?', (rows[-1][0],)).fetchone()[0])
    for e in (latest_raw['entries'].values() if isinstance(latest_raw['entries'], dict) else latest_raw['entries']):
        names[e['id']] = e.get('name', '')

    # the person's take-outs and keeps, with the version before each
    acts = []
    for at, a in cu.execute('select at, action from curation where by is null and reverted = 0 and at >= ? order by at',
                            (rows[0][1],)):
        d = json.loads(a)
        for s in d.get('steps', [d]):
            k, claim = s.get('action'), s.get('claim')
            if not claim:
                continue
            if k == 'check' and s.get('answer') in ('yes', 'no'):
                acts.append((at, 'keep' if s['answer'] == 'yes' else 'take-out', s.get('id'), claim))
            elif k in TAKE_OUTS:
                acts.append((at, 'take-out', s.get('source') if k == 'move' else s.get('id'), claim))
    print(f'actions: {sum(a[1] == "take-out" for a in acts)} take-outs, {sum(a[1] == "keep" for a in acts)} keeps',
          flush=True)
    ats = [r[1] for r in rows]
    import bisect
    need = defaultdict(list)
    for a in acts:
        i = bisect.bisect_left(ats, a[0]) - 1
        if i >= 0:
            need[rows[i][0]].append(a)
    SV, when = {}, dict(rows)
    for n, (vid, al) in enumerate(sorted(need.items())[:QUICK or None]):
        idx = Index(parse(cu.execute('select data from versions where id = ?', (vid,)).fetchone()[0]), when[vid], texts)
        SV[vid] = (idx, al)
        if n % 100 == 0:
            print(f'spread versions {n + 1}/{len(need)}', flush=True)
    for a in acts:
        texts.setdefault(a[3], len(texts))

    vec = vectors(texts)
    missing = {arm: int((~h).sum()) for arm, (_, h) in vec.items()}
    out.execute('insert into meta values (?,?)', ('texts', str(len(texts))))
    out.execute('insert into meta values (?,?)', ('missing', json.dumps(missing)))

    # growth: each version on its own claims
    per = {}
    for arm in ARMS:
        X, have = vec[arm]
        for label, idx in V.items():
            sp = Space(idx, X, have)
            res = {}
            for t, truth in idx.truth.items():
                if not have[t]:
                    continue
                r = rank_claim(sp.likeness(qvec(X, t), t), sp, truth, idx.anywhere[t])
                if r:
                    res[t] = r
            per[arm, label] = res
            for metric in ('r1', 'r12', 'r40', 'margin'):
                m, lo, hi = boot(np.array([r[metric] for r in res.values()]))
                save(out, 'growth', arm, label, metric, m, lo, hi, len(res))
            out.executemany('insert into claims values (?,?,?,?,?,?,?,?,?,?)',
                            [('growth', arm, label, str(t), r['r1'], r['r12'], r['r40'], r['margin'], r['own'], r['size'])
                             for t, r in res.items()])
            print(f'growth {arm} {label}: top-12 {np.mean([r["r12"] for r in res.values()]):.3f} '
                  f'margin {np.mean([r["margin"] for r in res.values()]):+.3f} over {len(res)}', flush=True)
        # the fixed set, paired
        a, b = per[arm, FIXED], per[arm, 'latest']
        both = sorted(set(a) & set(b))
        for metric in ('r1', 'r12', 'r40', 'margin'):
            diff = np.array([b[t][metric] - a[t][metric] for t in both])
            m, lo, hi = boot(diff)
            save(out, 'growth fixed', arm, f'latest - {FIXED}', metric, m, lo, hi, len(both))
            for label, src in ((FIXED, a), ('latest', b)):
                m2, lo2, hi2 = boot(np.array([src[t][metric] for t in both]))
                save(out, 'growth fixed', arm, label, metric, m2, lo2, hi2, len(both))
        # by the size of the claim's own motif (latest)
        for lo_s, hi_s in ((1, 2), (2, 3), (3, 6), (6, 10_000)):
            v = [r['r12'] for r in per[arm, 'latest'].values() if lo_s <= r['size'] < hi_s]
            m, lo, hi = boot(np.array(v))
            save(out, 'growth by size', arm, f'{lo_s}-{hi_s - 1}', 'r12', m, lo, hi, len(v))
        print(f'growth fixed {arm}: top-12 {np.mean([a[t]["r12"] for t in both]):.3f} -> '
              f'{np.mean([b[t]["r12"] for t in both]):.3f} over {len(both)}', flush=True)
    out.commit()

    # coverage
    L = V['latest']

    def final(m: str, merged: dict) -> str:
        seen = set()
        while m in merged and m not in seen:
            seen.add(m)
            m = merged[m]
        return m
    merged_all = {}
    for idx in V.values():
        merged_all.update(idx.merged)
    merged_all.update(L.merged)
    for cut in CUTS:
        D = V[cut]
        # placed by then: confirmed in some motif. Not merely filed: a machine filing the person later moved into a
        # motif carved for it is just the claim the index lacked a motif for
        held = {t for m in D.ids for t in D.confirmed[m]}
        live_then = {final(m, merged_all) for m in D.ids}
        new = [t for t in L.truth if t not in held]
        covered = [t for t in new if any(m in live_then for m in L.truth[t])]
        cov = set(covered)
        m, lo, hi = boot(np.array([t in cov for t in new], dtype=float))
        save(out, 'coverage', '-', cut, 'covered', m, lo, hi, len(new))
        for arm in ARMS:
            X, have = vec[arm]
            sp = Space(D, X, have)
            rs = []
            for t in covered:
                if not have[t]:
                    continue
                then = {m for m in D.ids if final(m, merged_all) in L.truth[t]}
                r = rank_claim(sp.likeness(qvec(X, t), None), sp, then, then)
                if r:
                    rs.append(r['r12'])
            m2, lo2, hi2 = boot(np.array(rs))
            save(out, 'coverage', arm, cut, 'covered r12', m2, lo2, hi2, len(rs))
        print(f'coverage {cut}: {len(covered)}/{len(new)} new claims had their motif', flush=True)
    out.commit()

    # spread
    for arm in ARMS:
        X, have = vec[arm]
        pos, neg, pos_own, neg_own = [], [], [], []
        for n, (vid, (idx, al)) in enumerate(SV.items()):
            sp = Space(idx, X, have)
            for at, kind, m, claim in al:
                t = texts[claim]
                if not have[t] or m not in sp.row or t not in idx.filed.get(m, []):
                    continue
                sim = sp.likeness(qvec(X, t), t)
                own = sim[sp.row[m]]  # the claim left out when it was a confirmed one
                if np.isnan(own):
                    continue
                others = np.delete(np.where(np.isnan(sim), -np.inf, sim),
                                   [sp.row[x] for x in idx.anywhere[t] if x in sp.row])
                margin = float(own - (others.max() if others.size else -1.0))
                (pos if kind == 'take-out' else neg).append(margin)
                (pos_own if kind == 'take-out' else neg_own).append(float(own))
                out.execute('insert into spread values (?,?,?,?,?,?,?)', (arm, at, kind, m, claim, margin, float(own)))
        # a take-out should sit far: low margin. AUC of -margin, take-outs as positives
        a, lo, hi = auc_boot([-x for x in pos], [-x for x in neg])
        save(out, 'spread', arm, '-', 'auc margin', a, lo, hi, len(pos) + len(neg))
        a, lo, hi = auc_boot([-x for x in pos_own], [-x for x in neg_own])
        save(out, 'spread', arm, '-', 'auc own', a, lo, hi, len(pos) + len(neg))
        save(out, 'spread', arm, '-', 'take-outs', len(pos))
        save(out, 'spread', arm, '-', 'keeps', len(neg))
        print(f'spread {arm}: AUC margin {auc([-x for x in pos], [-x for x in neg]):.3f} '
              f'({len(pos)} take-outs, {len(neg)} keeps)', flush=True)
    out.commit()

    # the map, on the latest index: motifs with 3+ confirmed claims
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    for arm in ARMS:
        X, have = vec[arm]
        sp = Space(L, X, have)
        keep = [i for i, m in enumerate(sp.mids) if sp.n[i] >= 3]
        mids = [sp.mids[i] for i in keep]
        C = sp.S[keep] / np.sqrt(np.maximum(sp.norm2[keep], 1e-12))[:, None]
        Sim = C @ C.T
        iu = np.triu_indices(len(mids), 1)
        sims = Sim[iu]
        kinds = defaultdict(list)
        for a_, b_ in zip(*iu):
            a, b = mids[a_], mids[b_]
            p = tuple(sorted((a, b)))
            kinds['related'].append(p in L.related)
            kinds['rests on'].append(b in L.parents.get(a, ()) or a in L.parents.get(b, ()))
            kinds['shared group'].append(bool(L.groups.get(a, set()) & L.groups.get(b, set())))
            ga, gb = L.genre.get(a), L.genre.get(b)
            kinds['one genre'].append(bool(ga) and ga == gb)
            kinds['not the same'].append(p in L.not_same)
        for kind, mask in kinds.items():
            mask = np.array(mask)
            a, lo, hi = auc_boot(sims[mask], sims[~mask])
            save(out, 'map', arm, 'latest', f'auc {kind}', a, lo, hi, int(mask.sum()))
        link = np.array(kinds['related']) | np.array(kinds['rests on'])
        a, lo, hi = auc_boot(sims[link], sims[~link])
        save(out, 'map', arm, 'latest', 'auc related or rests on', a, lo, hi, int(link.sum()))
        print(f'map {arm}: {len(mids)} motifs; ' + ', '.join(
            f'{k} {auc(sims[np.array(v)], sims[~np.array(v)]):.3f}' for k, v in kinds.items()), flush=True)
        # the closest unjudged pairs
        judged = np.array(kinds['related']) | np.array(kinds['rests on']) | np.array(kinds['not the same'])
        order = np.argsort(-sims)
        listed = 0
        for j in order:
            if judged[j]:
                continue
            out.execute('insert into pairs values (?,?,?,?,?)', (arm, mids[iu[0][j]], mids[iu[1][j]], float(sims[j]), ''))
            listed += 1
            if listed >= 40:
                break
        # clusters
        Z = linkage(squareform(np.clip(1 - Sim, 0, None), checks=False), method='average')
        for cut in (0.2, 0.3, 0.4, 0.5):
            lab = fcluster(Z, cut, criterion='distance')
            out.executemany('insert into clusters values (?,?,?,?,?)',
                            [(arm, cut, int(c), m, names.get(m, '')) for m, c in zip(mids, lab)])
            sizes = np.bincount(lab)[1:]
            save(out, 'map clusters', arm, 'latest', f'clusters at {cut}', len(sizes), None, None, int((sizes > 1).sum()))
        # the claims farthest from their centres (latest, motifs of 3+)
        if arm == LISTS:
            far = []
            for t, truth in L.truth.items():
                if not have[t]:
                    continue
                sim = sp.likeness(qvec(X, t), t)
                s = np.where(np.isnan(sim), -np.inf, sim)
                others = [(s[i], sp.mids[i]) for i in range(len(sp.mids)) if sp.mids[i] not in L.anywhere[t]]
                best_other = max(others) if others else (-1.0, '')
                for m in truth:
                    i = sp.row.get(m)
                    if i is None or sp.n[i] < 3 or np.isnan(sim[i]):
                        continue
                    far.append((float(sim[i] - best_other[0]), float(sim[i]), m, t, best_other[1]))
            rev = {v: k for k, v in texts.items()}
            far.sort()
            out.executemany('insert into far values (?,?,?,?,?,?,?)',
                            [(arm, m, names.get(m, ''), rev[t], mg, own, nb) for mg, own, m, t, nb in far[:60]])
    out.execute('insert into meta values (?,?)', ('finished', dt.now().isoformat(timespec='seconds')))
    out.commit()
    print('done', flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] != ['report']:
        sys.exit(__doc__)
    if '--quick' in sys.argv:
        QUICK, BOOTS, DB = 15, 10, DB.replace('.sqlite', '.quick.sqlite')
    report()
