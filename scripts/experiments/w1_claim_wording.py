"""W1 claim wording from the person's corrections (Oct 9). Each claim's one-line summary is written by a model from
its source (posts: Qwen3 8B, app/narratives.py; fact-checks: Qwen3 8B with the person's latest corrections as
examples, app/analysis/factchecks.py; shows and focus groups: Gemma 4 26B, show_claims.py and focus_group.py). The
person corrects them with ✎ (index['corrections'], 80 by Oct 9). Read together, the corrections fall into a handful of
kinds (RULES below, their examples made up: the corrections' own words would hand the test its answers). Here each corrected claim is written again from its source material, by both models, three ways:

- 'current': the source's own instruction (fact-checks with their production examples);
- 'rules': the same plus the rules read from the corrections;
- 'rules+examples': plus up to EXAMPLES of the person's corrections of the same kind of source;
- 'short' (Oct 10): rules+examples and a rule to write one short plain sentence, as the person does.

The correction under test, and any other correction to the same wording, is never among the examples. Scored against
the person's own wording: how alike (Qwen3-Embedding 8B, cosine), and a blind side-by-side (Nimble 9B: which of two
wordings is closer to the person's in what it says and how it frames it, asked both ways round) of each way against
'current' by the same model, and of the model's original wording (the 'before'). Resumable; caches in EXP."""
import json
import os
import random
import sys

import numpy as np
import requests as rq

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import tellings as tl  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'w1_claim_wording.json')
MODELS = ['qwen3:8b', 'gemma4:26b']
WAYS = ['current', 'rules', 'rules+examples', 'short']
EXAMPLES = 8
EMBED = 'qwen3-embedding:8b'
JUDGE = 'nimble:9b'

RULES = """How a person who curates these claims rewords them (follow it):
- Word what the tellers claim, never a fact-checker's verdict: "A video shows soldiers looting a church", not "A video \
of looting soldiers is from a film".
- Keep the part that makes it a story: the teller's "because", the charge, the consequence, the whole list ("...and \
nobody was punished", "...because the governor owed them a favor").
- Keep the teller's own strength and framing; don't soften it into a neutral paraphrase ("The banks are robbing \
ordinary savers", not "Banks offer low interest rates").
- Add nothing the tellers don't say: no motive, threat or framing of your own (if a mayor says he's disappointed in a newspaper, \
don't write that he threatened it).
- When the tellers disagree, word the argument itself: "Arguments over whether...", "Republicans debate whether...; \
many argue...", "Both sides say...".
- Allegations against people stay allegations: "accused", "critics say", "is said to"; never state a crime as fact. \
Name lesser-known people by their role ("a city councilman", "the plaintiff", "a former aide").
- If the claim says who says it, get it right: a guest, a host or a clip is not "the voter"; an aide is not the \
president.
- Spell names of people and organizations as they're usually written (transcripts mishear them), and give full names.
- Exact facts from the source: who sued whom, the amounts, the place.
- A stated concern is worded as the belief behind it ("elections should be paid for by citizens, not corporations", \
not "corporate money is a big issue")."""

# Oct 10: both models wrote longer than the person (W1's first run), and no rule said so
SHORT = """- Write it as the person does: one short, plain sentence, usually under 20 words, saying what is claimed, not \
who reports it or where it circulates ("A video shows a crowd storming a stadium", not "Social media posts claim a \
video shows a crowd storming a stadium"); leave out dates, places and numbers unless the claim turns on them."""

CURRENT = {
    'folklore': 'The claim or story most of the posts share, in one plain sentence.',
    'fact-check': ('The claim or rumor it checks, the way the people spreading it state it: what they say is true ("the '
                   'moon landing was staged"), never the fact-checker\'s correction or verdict ("the moon landing photos '
                   'are genuine"). One or two plain sentences, as full as the piece shows it: who says it (a politician, '
                   'posts on social media, a viral video) and in what setting when that\'s part of the story, and what '
                   'exactly they say, not the headline\'s shorthand.'),
    'radio & podcasts': ('The claim told in the quoted words, in one plain sentence, the way it\'s told: what the speaker '
                         'says is true. Name who it\'s about as the speaker means it ("Democrats", "Trump", "the Fed"), '
                         'never "the speaker", "the host", "the voter" or "his opponents", and without saying who says it '
                         '("Tariffs raised prices", not "The host says tariffs raised prices").'),
    'focus-group': ('The claim told in the quoted words: one plain sentence of what is said to be true or believed, in '
                    'the teller\'s own terms, without saying who says it ("Defunding the police isn\'t a federal issue", '
                    'not "The voter believes defunding the police isn\'t a federal issue"; never "the voter", "the '
                    'speaker" or "the person").'),
}
SCHEMA = {"type": "object", "properties": {"claim": {"type": "string", "maxLength": 400}}, "required": ["claim"]}


def material(claim: str) -> tuple[str, str]:
    """(kind, the source as the writing model would read it) for a claim"""
    d = tl._validate().claim_detail(claim)
    kind = d.get('kind', '')
    cut = lambda t, n: ' '.join(str(t or '').split())[:n]  # noqa: E731
    if kind == 'focus-group':
        return kind, (f'Part of a podcast that plays recordings of focus groups of voters ({d.get("title")}):\n'
                      f'{cut(d.get("context") or d.get("quote"), 1600)}\n\nThe quoted words: "{d.get("quote")}"')
    if kind == 'radio & podcasts':
        parts = [f'{t["show"]} ({t.get("speaker") or "someone"}): {cut(t.get("context") or t.get("quote"), 900)}\n'
                 f'The quoted words: "{t.get("quote")}"' for t in (d.get('tellings') or [])[:2]]
        return kind, 'Parts of shows:\n' + '\n\n'.join(parts)
    if kind == 'fact-check':
        return kind, (f'A fact-checker published this:\n{d.get("title")}\n{cut(d.get("summary"), 400)}\n'
                      f'The piece itself:\n{cut(d.get("piece"), 1500)}')
    if kind == 'folklore':
        posts = [p['text'] for p in (d.get('all_posts') or []) if not p.get('reply')][:10] or d.get('examples') or []
        return kind, 'These posts were written by different people:\n' + '\n'.join(f'- {cut(p, 280)}' for p in posts)
    return kind, ''


def items() -> list[dict]:
    """One per corrected wording (the person's): its source, the model's wordings it replaced, its kind"""
    index = mi.load()
    by = {}
    for old, new in index.get('corrections', {}).items():
        if old != new and len(old) < 400 and len(new) < 400:
            by.setdefault(new, []).append(old)
    out = []
    for new, olds in by.items():
        kind, text = material(new)
        if text:
            out.append({'key': mi.key(new), 'person': new, 'before': olds, 'kind': kind, 'material': text})
    return out


def examples(item: dict, every: list[dict]) -> str:
    same = [x for x in every if x['kind'] == item['kind'] and x['person'] != item['person']
            and not set(x['before']) & set(item['before'])][-EXAMPLES:]
    if not same:
        return ''
    return ('\nHow the person corrected claims from the same kind of source before (do as they did):\n'
            + '\n'.join(f'- "{x["before"][-1]}" became "{x["person"]}"' for x in same))


def prompt(item: dict, way: str, every: list[dict]) -> str:
    extra = ''
    if way == 'current' and item['kind'] == 'fact-check':
        extra = examples(item, every)  # production gives fact-checks the latest corrections already
    elif way == 'rules':
        extra = '\n\n' + RULES
    elif way == 'rules+examples':
        extra = '\n\n' + RULES + '\n' + examples(item, every)
    elif way == 'short':
        extra = '\n\n' + RULES + '\n' + SHORT + '\n' + examples(item, every)
    return f"{item['material']}\n\nclaim: {CURRENT[item['kind']]}{extra}"


def write(model: str, p: str) -> str | None:
    a = llm.complete_json(p, SCHEMA, max_tokens=400, model=model)
    return ' '.join(a['claim'].split()) if a and a.get('claim') else None


def embed(texts: list[str]) -> np.ndarray:
    r = rq.post(f'{llm.OLLAMA_URL}/api/embed', json={'model': EMBED, 'input': texts}, timeout=600)
    r.raise_for_status()
    v = np.array(r.json()['embeddings'], dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def closer(person: str, a: str, b: str) -> float:
    """P(a is closer than b to the person's wording), asked both ways round"""
    def ask(x, y):
        state = f'The person\'s wording of a claim: {person}\n\nWording A: {x}\nWording B: {y}'
        r = rq.post(f'{llm.OLLAMA_URL}/v1/systemone', timeout=300, json={'model': JUDGE, 'state': state, 'questions': {
            'q': {'type': 'noul', 'instructions': 'Is wording A closer than wording B to the person\'s wording, in what '
                                                  'it says and how it frames it (who says it, how strongly, what is '
                                                  'claimed, what is left out)?'}}})
        r.raise_for_status()
        v = r.json()['answers']['q']
        return float(v.get('noul', v.get('probability')) if isinstance(v, dict) else v)
    return (ask(a, b) + 1 - ask(b, a)) / 2


def main():
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    every = items()
    print(f'{len(every)} corrected wordings with their source', flush=True)
    got = saved.setdefault('written', {})
    jobs = [(m, w, it) for m in MODELS for w in WAYS for it in every if f'{m}|{w}|{it["key"]}' not in got]
    for model in MODELS:  # one model at a time, so it loads once
        mine = [(w, it) for m, w, it in jobs if m == model]
        for s in range(0, len(mine), 32):
            part = mine[s:s + 32]
            out = llm.parallel(lambda x, model=model: write(model, prompt(x[1], x[0], every)), part)
            for (w, it), v in zip(part, out):
                if v:
                    got[f'{model}|{w}|{it["key"]}'] = v
            json.dump(saved, open(OUT, 'w'))
            print(f'{model}: {sum(k.startswith(model) for k in got)}/{len(WAYS) * len(every)}', flush=True)
    sims = saved.setdefault('similar', {})
    texts = {}
    for it in every:
        texts[f'person|{it["key"]}'] = it['person']
        texts[f'before|{it["key"]}'] = it['before'][-1]
        for m in MODELS:
            for w in WAYS:
                k = f'{m}|{w}|{it["key"]}'
                if k in got:
                    texts[k] = got[k]
    todo = [k for k in texts if k not in sims and not k.startswith('person|')]
    if todo:
        V = dict(zip(texts, embed(list(texts.values()))))
        for k in todo:
            sims[k] = float(V[k] @ V[f'person|{k.split("|")[-1]}'])
        json.dump(saved, open(OUT, 'w'))
    sides = saved.setdefault('sides', {})
    pairs = []
    for it in every:
        for m in MODELS:
            cur = got.get(f'{m}|current|{it["key"]}')
            for w in WAYS[1:]:
                k = f'{m}|{w}|{it["key"]}'
                if cur and k in got and k not in sides:
                    pairs.append((k, it['person'], got[k], cur))
            k = f'{m}|current-vs-before|{it["key"]}'
            if cur and k not in sides:
                pairs.append((k, it['person'], cur, it['before'][-1]))
    for s in range(0, len(pairs), 32):
        part = pairs[s:s + 32]
        for (k, *_), v in zip(part, llm.parallel(lambda x: closer(*x[1:]), part)):
            if v is not None:
                sides[k] = round(v, 4)
        json.dump(saved, open(OUT, 'w'))
        print(f'sides {len(sides)}', flush=True)
    for ln in report(saved, every):
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


def report(saved, every):
    sims, sides = saved['similar'], saved['sides']
    kinds = sorted({it['kind'] for it in every})
    lines = [f'W1 claim wording, {len(every)} of the person\'s corrected wordings '
             f'({", ".join(f"{k} {sum(it["kind"] == k for it in every)}" for k in kinds)}):',
             '  likeness to the person\'s wording (cosine, mean; the model\'s original wording: '
             f'{np.mean([sims[f"before|{it["key"]}"] for it in every]):.3f}):']
    for m in MODELS:
        lines.append(f'    {m}: ' + ', '.join(
            f'{w} {np.mean([sims[k] for it in every if (k := f"{m}|{w}|{it["key"]}") in sims]):.3f}'
            for w in WAYS))
    lines.append('  side by side, how often closer to the person\'s than the same model\'s current wording '
                 '(share of claims; 0.5 = no better):')
    for m in MODELS:
        row = []
        for w in WAYS[1:]:
            v = [sides[f'{m}|{w}|{it["key"]}'] for it in every if f'{m}|{w}|{it["key"]}' in sides]
            row.append(f'{w} {np.mean([x > 0.5 for x in v]):.2f} (mean {np.mean(v):.2f}, n {len(v)})')
        v = [sides[f'{m}|current-vs-before|{it["key"]}'] for it in every if f'{m}|current-vs-before|{it["key"]}' in sides]
        row.append(f'current against the original wording {np.mean([x > 0.5 for x in v]):.2f}')
        lines.append(f'    {m}: ' + '; '.join(row))
    words = lambda t: len(str(t).split())  # noqa: E731
    lines.append(f'  words a wording (mean): the person {np.mean([words(it["person"]) for it in every]):.1f}; ' + '; '.join(
        f'{m} ' + ', '.join(f'{w} {np.mean([words(saved["written"][k]) for it in every if (k := f"{m}|{w}|{it["key"]}") in saved["written"]]):.1f}'
                            for w in WAYS) for m in MODELS))
    for kind in kinds:
        its = [it for it in every if it['kind'] == kind]
        lines.append(f'  {kind} ({len(its)}): ' + '; '.join(
            f'{m} ' + ', '.join(f'{w} {np.mean([sims.get(f"{m}|{w}|{it["key"]}", np.nan) for it in its]):.3f}' for w in WAYS)
            for m in MODELS))
    random.seed(0)
    for it in random.sample(every, min(4, len(every))):
        lines.append(f'  e.g. person: {it["person"][:160]}')
        for m in MODELS:
            lines.append(f'    {m} current: {saved["written"].get(f"{m}|current|{it["key"]}", "")[:160]}')
            lines.append(f'    {m} rules+examples: {saved["written"].get(f"{m}|rules+examples|{it["key"]}", "")[:160]}')
    return lines


if __name__ == '__main__':
    main()
