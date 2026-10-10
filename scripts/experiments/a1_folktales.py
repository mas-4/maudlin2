"""A1 the filing machinery on a codebook that isn't ours (Oct 10). Bag-of-Tales (Hagedorn and Darányi, Journal of
Open Humanities Data 2022; github j-hagedorn/trilogy): 1,518 folktales from Ashliman's Folktexts, each labelled by
folklorists with its ATU tale type, 182 types among them; the codebook is the ATU index, 2,247 types, each with a name
and a description. Our pipeline run on it as on our own index, nothing retrained:
- the claim: Gemma 26B sums each tale up as a claim, in one plain sentence (as our claims are) or in three (does the
  one sentence lose what tells tale types apart?);
- the shortlist: the learned shortlist's production weights (motif_retriever), each type a motif whose note is its
  ATU description and whose claims are the other tales of that type (the tale's own left out). Against plain likeness
  of the claim to the type's description and claims, and over the 182 types with tales (every motif of ours has claims)
  as well as all 2,247 (most of them seeds, a description only);
- the pick: Gemma 26B with production's prompt (motif_index.REUSE_PROMPT) over the shortlist's 8 best of the types
  with tales, as name_claim shows them;
- the judge: Nimble 9B with each type's must-have element (drafted by Gemma from its name and description, as
  production drafts ours), on the right type and the four best wrong ones of a sample of tales.
Measured against the folklorists' labels: recall at 8, 12 and 40, the pick's hits and wrong picks, the judge's AUC.
The machinery only: folktales are a closed genre, the person's index covers all public speech (their caution, Oct 10).
Stages, each resumable and under two hours (the lease's limit); answers cached in EXP:
    a1_folktales.py claims | picks | judge | report"""
import json
import os
import random
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import d1_definition_swap as d1  # noqa: E402
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402
from app.utils import Config  # noqa: E402

DATA = os.path.join(Config.data, 'archives', 'trilogy')
OUT = os.path.join(harness.EXP, 'a1_folktales.json')
ARMS = {'one sentence': 'in one plain sentence', 'three sentences': 'in three plain sentences'}
WORDS = 1500  # of a tale, at most
SHOWN = 8  # the pick's options, as production's shortlist shows
JUDGED = 600  # tales the judge is asked about, a sample
WRONG = 4  # wrong types judged beside the right one
CLAIM_PROMPT = """A tale people tell:
{text}

Sum up the story it tells, {length}, as someone retelling it would put it: who does what, and what comes of it."""
CLAIM_SCHEMA = {"type": "object", "properties": {"claim": {"type": "string", "maxLength": 900}}, "required": ["claim"]}


def load() -> tuple[pd.DataFrame, dict]:
    tales = pd.read_csv(os.path.join(DATA, 'aft.csv')).dropna(subset=['text', 'atu_id']).reset_index(drop=True)
    tales['atu_id'] = tales['atu_id'].astype(str)
    atu = pd.read_csv(os.path.join(DATA, 'atu_df.csv'))
    atu['atu_id'] = atu['atu_id'].astype(str)
    types = {r.atu_id: {'id': r.atu_id, 'name': str(r.tale_name), 'note': ' '.join(str(r.tale_type).split()) if
                        isinstance(r.tale_type, str) else '', 'phrases': [], 'claims': []} for r in atu.itertuples()}
    return tales, types


def save(saved):
    json.dump(saved, open(OUT, 'w'))


def claims(saved, tales):
    for arm, length in ARMS.items():
        got = saved.setdefault('claims', {}).setdefault(arm, {})
        todo = [(str(i), ' '.join(t.split()[:WORDS])) for i, t in enumerate(tales['text']) if str(i) not in got]
        for start in range(0, len(todo), 32):
            part = todo[start:start + 32]
            asks = llm.parallel(lambda x, length=length: llm.complete_json(
                CLAIM_PROMPT.format(text=x[1], length=length), CLAIM_SCHEMA, max_tokens=600, model=ms.JUDGE_MODEL), part)
            for (i, _), a in zip(part, asks):
                if a and a.get('claim'):
                    got[i] = ' '.join(a['claim'].split())
            save(saved)
            print(f'claims, {arm}: {len(got)}/{len(tales)}', flush=True)


def index_of(tales, types, said: dict) -> dict:
    """The types as motifs, each holding its tales' claims"""
    entries = {k: {**v, 'claims': []} for k, v in types.items()}
    for i, t in enumerate(tales['atu_id']):
        if str(i) in said and t in entries:
            entries[t]['claims'].append({'claim': said[str(i)], 'tale': i})
    return entries


def rankings(tales, types, said, vec, w) -> dict:
    """{tale: {'learned': [type ids, best first], 'plain': [...], 'learned, with tales': [...]}}"""
    entries = index_of(tales, types, said)
    order = list(entries)
    with_tales = np.array([len(entries[k]['claims']) > 0 for k in order])
    weights = np.array([w['weights'][f] for f in mr.FACTS])
    out = {}
    for i in range(len(tales)):
        c = said.get(str(i))
        if not c:
            continue
        F = mr.facts([entries[k] for k in order], c, vec, leave_out=True)
        learned = F @ weights + w['bias']
        plain = F[:, :2].max(1)
        alone = with_tales & np.array([any(x['tale'] != i for x in entries[k]['claims']) for k in order])
        out[str(i)] = {'learned': [order[j] for j in np.argsort(-learned)[:40]],
                       'plain': [order[j] for j in np.argsort(-plain)[:40]],
                       'learned, with tales': [order[j] for j in np.argsort(-np.where(alone, learned, -1e9))[:40]]}
        if i % 200 == 0:
            print(f'shortlists {i}/{len(tales)}', flush=True)
    return out


def picks(saved, tales, types):
    from datetime import datetime
    w = mr.weights()
    vec = mr.Vectors()
    for arm in ARMS:
        said = saved['claims'][arm]
        ranks = saved.setdefault('ranks', {}).get(arm)
        if not ranks or len(ranks) < len(said):
            ranks = saved['ranks'][arm] = rankings(tales, types, said, vec, w)
            save(saved)
        entries = index_of(tales, types, said)
        got = saved.setdefault('picks', {}).setdefault(arm, {})

        def pick(i, entries=entries, ranks=ranks, said=said):
            shown = [entries[k] for k in ranks[i]['learned, with tales'][:SHOWN]]
            options = '\n'.join(f'{n}. {mi.described(e)}\n' + '\n'.join(
                f'   - {c["claim"][:160]}' for c in [x for x in e['claims'] if x['tale'] != int(i)][-3:])
                for n, e in enumerate(shown, 1))
            schema = {"type": "object", "properties": {
                "reason": {"type": "string", "maxLength": 1000},
                "fits": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": len(shown)}}},
                "required": ["reason", "fits"]}
            a = llm.complete_json(mi.REUSE_PROMPT.format(today=datetime.now().strftime('%B %-d, %Y'), claim=said[i],
                                                         options=options), schema, max_tokens=900, model=ms.JUDGE_MODEL)
            return None if a is None else [shown[n - 1]['id'] for n in dict.fromkeys(a.get('fits', [])) if 1 <= n <= len(shown)]
        todo = [i for i in ranks if i not in got]
        for start in range(0, len(todo), 32):
            part = todo[start:start + 32]
            for i, a in zip(part, llm.parallel(pick, part)):
                if a is not None:
                    got[i] = a
            save(saved)
            print(f'picks, {arm}: {len(got)}/{len(ranks)}', flush=True)


def judge(saved, tales, types):
    vec = mr.Vectors()
    sample = sorted(saved['ranks']['one sentence'], key=lambda i: random.Random(i).random())[:JUDGED]
    need = {t for arm in ARMS for i in sample for t in [tales['atu_id'][int(i)]] + saved['ranks'][arm][i]['learned, with tales'][:WRONG + 1]}
    elements = saved.setdefault('elements', {})

    def draft(t):
        e = types[t]
        a = llm.complete_json(ms.ELEMENT_PROMPT.format(name=e['name'], genre='Tale type',
                                                       note=e['note'] or '(no note yet)'),
                              ms.ELEMENT_SCHEMA, max_tokens=200, model=ms.JUDGE_MODEL)
        return ' '.join(a['element'].split()) if a and a.get('element') else None
    todo = sorted(t for t in need if t not in elements)
    for start in range(0, len(todo), 32):
        part = todo[start:start + 32]
        for t, a in zip(part, llm.parallel(draft, part)):
            if a:
                elements[t] = a
        save(saved)
        print(f'elements: {len(elements)}/{len(need)}', flush=True)
    for arm in ARMS:
        said = saved['claims'][arm]
        entries = index_of(tales, types, said)
        got = saved.setdefault('judged', {}).setdefault(arm, {})
        asks = []
        for i in sample:
            right = tales['atu_id'][int(i)]
            wrong = [t for t in saved['ranks'][arm][i]['learned, with tales'] if t != right][:WRONG]
            for t in [right] + wrong:
                k = f'{i}|{t}'
                if k in got or t not in elements:
                    continue
                e = entries[t]
                others = [x['claim'] for x in e['claims'] if x['tale'] != int(i)]
                near = [others[j] for j in np.argsort(-(vec(others) @ vec([said[i]])[0]))[:3]] if others else []
                text = (f"Motif: {e['name']}\nWhat it covers: {e['note'] or '(no note yet)'}\n"
                        f"{ms.ELEMENT_LINE} {elements[t]}\nClaims filed under it:\n"
                        + '\n'.join(f'- {c[:300]}' for c in near) + f'\n\nNew claim: {said[i]}')
                asks.append((k, text))
        for start in range(0, len(asks), 32):
            part = asks[start:start + 32]
            for (k, _), v in zip(part, llm.parallel(lambda x: d1.nimble(x[1], ms.ELEMENT_QUESTION), part)):
                if v is not None:
                    got[k] = v
            save(saved)
            print(f'judged, {arm}: {len(got)} ({len(asks)} asked this run)', flush=True)


def report(saved, tales):
    from sklearn.metrics import roc_auc_score
    lines = [f'A1 our machinery on folktales (Bag-of-Tales, {len(tales)} tales, {tales["atu_id"].nunique()} ATU types '
             f'of 2,247), against the folklorists\' labels:']
    for arm in ARMS:
        ranks = saved.get('ranks', {}).get(arm, {})
        if not ranks:
            continue
        truth = {i: tales['atu_id'][int(i)] for i in ranks}
        has_others = {i for i in ranks if (tales['atu_id'] == truth[i]).sum() > 1}
        parts = []
        for name in ('plain', 'learned', 'learned, with tales'):
            pool = [i for i in ranks if name != 'learned, with tales' or i in has_others]
            parts.append(f"{name} " + '/'.join(f"{np.mean([truth[i] in ranks[i][name][:k] for i in pool]):.0%}" for k in (8, 12, 40)))
        lines.append(f'  {arm}: shortlist recall at 8/12/40: ' + '; '.join(parts)
                     + f' (the last over the {len(has_others)} tales whose type has others)')
        got = saved.get('picks', {}).get(arm, {})
        if got:
            pool = [i for i in got if i in has_others]
            right = np.mean([truth[i] in got[i] for i in pool])
            none = np.mean([not got[i] for i in pool])
            wrong = np.mean([len([t for t in got[i] if t != truth[i]]) for i in pool])
            shown = np.mean([truth[i] in ranks[i]['learned, with tales'][:SHOWN] for i in pool])
            lines.append(f'  {arm}: the pick (Gemma 26B, {len(pool)} tales): the right type {right:.0%} (it was among the '
                         f'{SHOWN} shown for {shown:.0%}), none {none:.0%}, {wrong:.2f} wrong picks a tale')
        j = saved.get('judged', {}).get(arm, {})
        if j:
            y = np.array([k.split('|')[1] == truth[k.split('|')[0]] for k in j])
            v = np.array(list(j.values()))
            lines.append(f'  {arm}: the judge (Nimble 9B with elements, {len(j)} pairs, {int(y.sum())} right): AUC '
                         f'{roc_auc_score(y, v):.3f}; yes on the right type {v[y].mean():.2f}, on wrong ones {v[~y].mean():.2f}')
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)


def main():
    tales, types = load()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    stage = sys.argv[1] if len(sys.argv) > 1 else 'report'
    if stage == 'claims':
        claims(saved, tales)
    elif stage == 'picks':
        picks(saved, tales, types)
    elif stage == 'judge':
        judge(saved, tales, types)
    report(saved, tales)
    print('DONE', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f'{(time.time() - t0) / 60:.0f} min', flush=True)
