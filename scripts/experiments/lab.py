"""The experiments page's data (Oct 12, the person: "I need you to build some dashboard system ... to be able to examine
this stuff ... I almost never see results from our experiment except second hand from you"). The checker serves it at
/experiments (scripts/validate.py): the catalog and its result lines, the queue, Ma'at's weighings, the stories cut in
production, each experiment's paper (~/maudlin-data/papers), and its cases: the items it was tested on with what
happened to each, so the failures can be read one by one, sorted into their kinds. Read-only, but for the person's
verdicts on Pandora's proposed tellings.

A new experiment gets cases by adding a function to CASES: code -> () -> {'summary': [(label, n)], 'columns': [...],
'rows': [{'kind': failure kind or 'ok', 'cells': [...]}], 'note': how to read it}."""
import json
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.utils import Config  # noqa: E402

EXP = harness.EXP
PAPERS = os.path.join(Config.data, 'papers')
CATALOG = os.path.join(EXP, 'experiments.sqlite')
LIMIT = 400  # rows a case table sends


def capped(rows: list[dict]) -> list[dict]:
    """At most LIMIT rows of each kind, in order"""
    seen = Counter()
    out = []
    for r in rows:
        seen[r['kind']] += 1
        if seen[r['kind']] <= LIMIT:
            out.append(r)
    return out


def _load(name: str) -> dict:
    path = os.path.join(EXP, name)
    return json.load(open(path)) if os.path.exists(path) else {}


def overview() -> dict:
    from codenames import figure_of
    con = sqlite3.connect(f'file:{CATALOG}?mode=ro', uri=True)
    rows = con.execute('select code, codename, why, family, name, status, result, script from experiments').fetchall()
    lines = {}
    for at, code, line in con.execute('select at, code, line from results order by at'):
        lines.setdefault(code, []).append({'at': at, 'line': re.sub(r'^\S+ ', '', line, count=1) if code else line})
    try:
        queue = [{'id': i, 'step': figure_of(h), 'status': s, 'tries': t, 'started': st, 'finished': f}
                 for i, h, s, t, st, f in con.execute('select id, holder, status, tries, started, finished from queue '
                                                      'order by priority desc, id')]
    except sqlite3.OperationalError:
        queue = []
    experiments = [{'code': c, 'figure': fig or c, 'why': why or '', 'family': fam or '', 'question': name, 'status': st,
                    'result': res or '', 'script': sc or '', 'lines': lines.get(c, [])[-12:], 'cases': c in CASES,
                    'paper': bool(paper_path(fig or c))} for c, fig, why, fam, name, st, res, sc in rows]
    return {'experiments': experiments, 'queue': queue, 'maat': _load('maat_history.json') or [],
            'seams': seams_today()}


def paper_path(figure: str) -> str | None:
    """The paper whose title names the figure (one paper may cover several: Aesop, Loki and Hermagoras)"""
    if not os.path.isdir(PAPERS):
        return None
    want = figure.lower().removeprefix('the ').strip()
    for name in sorted(os.listdir(PAPERS)):
        if name.endswith('.md') and not name.startswith('00'):
            with open(os.path.join(PAPERS, name)) as f:
                title = f.readline().lower()
            if want in title:
                return os.path.join(PAPERS, name)
    return None


def paper(code: str) -> dict:
    con = sqlite3.connect(f'file:{CATALOG}?mode=ro', uri=True)
    row = con.execute('select codename from experiments where code = ?', (code,)).fetchone()
    path = paper_path(row[0] if row and row[0] else code)
    if not path:
        return {'text': '', 'file': None}
    return {'text': open(path).read(), 'file': os.path.basename(path),
            'pipeline': open(os.path.join(PAPERS, '00-pipeline.md')).read()}


def seams_today() -> list[dict]:
    """The stories production cut (or didn't) at a seam: each cut the judge was asked about, with its answer"""
    from app.utils.store import read_json
    cache = read_json(os.path.join(Config.data, 'story_seams.json'), {})
    out = []
    for v in cache.values():
        if len(v) >= 5:
            out.append({'cut': not v[0] and not v[1], 'one_event': v[:2], 'reason': v[2], 'a': v[3], 'b': v[4]})
    return out[-60:]


# ---------- cases ----------

def scheherazade() -> dict:
    """Each folktale: its type, where the right type stood in the shortlist, what Gemma picked"""
    import pandas as pd
    saved = _load('a1_folktales.json')
    data = os.path.join(Config.data, 'archives', 'trilogy')
    tales = pd.read_csv(os.path.join(data, 'aft.csv')).dropna(subset=['text', 'atu_id']).reset_index(drop=True)
    tales['atu_id'] = tales['atu_id'].astype(str)
    atu = pd.read_csv(os.path.join(data, 'atu_df.csv'))
    names = {str(r.atu_id): str(r.tale_name) for r in atu.itertuples()}
    arm = 'one sentence'
    said, ranks, picks = saved['claims'][arm], saved['ranks'][arm], saved.get('picks', {}).get(arm, {})
    counts = tales['atu_id'].value_counts()
    rows = []
    for i, r in ranks.items():
        truth = tales['atu_id'][int(i)]
        if counts[truth] < 2:
            continue  # its type has no other tale: as the report, the type-with-tales pool
        shortlist = r['learned, with tales']
        at = shortlist.index(truth) + 1 if truth in shortlist else None
        got = picks.get(i)
        if got is None:
            continue
        if truth in got:
            kind = 'ok'
        elif at is None or at > 8:
            kind = 'the right type was never shown (shortlist)'
        elif not got:
            kind = 'shown, but Gemma picked nothing'
        else:
            kind = 'shown, but Gemma picked another type'
        picked = '; '.join(f'{t} {names.get(t, "")}' for t in got) or '—'
        rows.append({'kind': kind, 'cells': [tales['tale_title'][int(i)], said.get(i, ''), f'{truth} {names.get(truth, "")}',
                                             at or '40+', picked]})
    summary = Counter(r['kind'] for r in rows).most_common()
    confused = Counter((r['cells'][2], r['cells'][4]) for r in rows if r['kind'] == 'shown, but Gemma picked another type')
    note = ('Each tale summed up as a one-sentence claim, its ATU type the answer. "Shortlist" failures: the right type '
            'wasn\'t among the 8 Gemma was shown. "Pick" failures: it was shown and Gemma chose otherwise. The types '
            'most often confused: ' + '; '.join(f'{a} taken for {b} ({n})' for (a, b), n in confused.most_common(6)))
    rows.sort(key=lambda r: (r['kind'] == 'ok', r['kind']))
    return {'summary': summary, 'columns': ['tale', 'its claim', 'right type', 'right type in the shortlist', 'Gemma picked'],
            'rows': capped(rows), 'note': note}


def atropos() -> dict:
    """Each cut of a week's stories: its score, the two sides, Gemma's verdict under both wordings"""
    s = _load('s4_story_seams.json')
    judged = s.get('judged', {})
    rows = []
    for c in sorted(s.get('cuts', []), key=lambda c: c['ncut']):
        v = judged.get(json.dumps([c['a'], c['b']]))
        if not v:
            continue
        if v[0] != v[1]:
            kind = 'the two wordings disagree'
        elif c['ncut'] < 0.6:
            kind = 'ok' if not v[0] else 'under 0.6 but one event (a wrong cut)'
        else:
            kind = 'ok' if v[0] else 'over 0.6 but two events (a missed cut)'
        rows.append({'kind': kind, 'cells': [c['ncut'], c['label'], ' · '.join(c['a'][:3]), ' · '.join(c['b'][:3]),
                                             'one event' if v[0] else 'two events', v[2] if len(v) > 2 else '']})
    return {'summary': Counter(r['kind'] for r in rows).most_common(),
            'columns': ['cut score', 'story', 'side A', 'side B', 'Gemma', 'why'], 'rows': capped(rows),
            'note': 'Lower scores are cleaner cuts. Production cuts only under 0.6, and only when Gemma says two events '
                    'both ways.'}


def gordian_knot() -> dict:
    s = _load('f1_gordian_knot.json')
    rows = [{'kind': 'ok' if o['rank'] == 1 else 'the carved claim was not the least alike',
             'cells': [o['motif'], o['size'], o['rank']]} for o in s.get('odd', [])]
    return {'summary': Counter(r['kind'] for r in rows).most_common(),
            'columns': ['motif carved from', 'claims then', "the carved claim's rank (1 = least alike)"],
            'rows': capped(rows), 'note': 'Word likeness (TF-IDF) within the motif as it stood before the carve. Chance '
                                          'puts the carved claim first about 1 time in the motif\'s size.'}


def chimera() -> dict:
    from app.analysis import motif_index as mi
    names = {e['id']: e['name'] for e in mi.live(mi.load())}
    rows = []
    for claim, v in _load('f8_chimera.json').get('claims', {}).items():
        subs = v.get('subs') or []
        tells = v.get('tells') or []
        landing = '; '.join(f"{names.get(m, m)} → {('#' + str(t)) if t > 0 else 'none' if t == 0 else 'all'}"
                            for m, t in zip(v['motifs'], tells)) if tells else ''
        kind = ('one claim' if len(subs) < 2 else
                'motifs on different claims' if len({t for t in tells if t > 0}) >= 2 else
                'motifs on one claim' if tells else 'split')
        rows.append({'kind': kind if v['kind'] == '3+ motifs' else f'(one motif) {kind}',
                     'cells': [v['kind'], claim, v['posts'], ' | '.join(f"#{n} {s['claim']}" for n, s in enumerate(subs, 1)),
                               ', '.join(names.get(m, m) for m in v['motifs']), landing]})
    return {'summary': Counter(r['kind'] for r in rows).most_common(),
            'columns': ['filed in', 'the claim written for the group', 'posts', 'the claims Gemma found in the posts',
                        "your motifs", 'which found claim tells each motif'], 'rows': capped(rows),
            'note': 'Gemma read every post behind the claim and listed the distinct claims two or more posts make.'}


def pandora() -> dict:
    s = _load('f10_pandora.json')
    verdicts = s.get('verdicts', {})
    rows = []
    controls = {}
    for c in s.get('controls', []):  # random groups named the same way, mixed in unlabelled (the baseline)
        controls.setdefault(c['motif'], []).append(c)
    for mid, m in s.get('motifs', {}).items():
        told = [(f"{mid}|{g['name']}", g) for g in m['groups']] + [(f"ctl|{mid}|{c['name']}", c) for c in controls.get(mid, [])]
        for key, g in sorted(told, key=lambda kg: kg[1]['name'].lower()):
            rows.append({'kind': verdicts.get(key, 'to judge'), 'key': key, 'verdict': verdicts.get(key),
                         'cells': [f"{m['name']} ({m['claims']})", g['name'], g['note'], len(g['claims']),
                                   ' · '.join(g['claims'][:6])]})
    return {'summary': Counter(r['kind'] for r in rows).most_common(), 'judge': 'F10',
            'columns': ['your motif (claims)', 'proposed telling', 'its shape', 'claims', 'its claims'], 'rows': rows,
            'note': 'Gemma opened each of your motifs of 10+ claims and named the tellings inside. Judge each: worth a '
                    'motif of its own (resting on yours), already a motif, or not a telling. Nothing changes your index.'}


CASES = {'A1': scheherazade, 'S4': atropos, 'F1': gordian_knot, 'F8': chimera, 'F10': pandora}


def cases(code: str) -> dict:
    fn = CASES.get(code)
    if not fn:
        return {'rows': [], 'columns': [], 'summary': [], 'note': 'No case-by-case record for this one yet.'}
    try:
        return fn()
    except (OSError, KeyError, ValueError) as e:
        return {'rows': [], 'columns': [], 'summary': [], 'note': f'Not readable yet ({type(e).__name__}: {e}).'}


def verdict(code: str, key: str, value: str | None) -> dict:
    """The person's verdict on one of an experiment's items (Pandora's tellings: 'motif', 'already' or 'not')"""
    if code != 'F10' or value not in ('motif', 'already', 'not', None):
        raise ValueError('only Pandora takes verdicts: motif, already or not')
    path = os.path.join(EXP, 'f10_pandora.json')
    s = json.load(open(path))
    v = s.setdefault('verdicts', {})
    if value is None:
        v.pop(key, None)
    else:
        v[key] = value
    json.dump(s, open(path + '.tmp', 'w'), indent=1)
    os.replace(path + '.tmp', path)
    return {'ok': True, 'verdicts': len(v)}
