"""G1 genre descriptions (Oct 9). The genre drafter (motif_proposals.GENRE_PROMPT, Gemma 4 26B) sees each genre only as
five of the person's motifs in it. docs/motif-praxis.md now says what each genre is, as the person's sorting has shown
it, with the Plot/Theory, Belief/Theory and Argument/Archetype tests; it says to give the drafter these once they
settle, measured against the person's own genre calls. Here every motif the person gave a genre is asked again (left
out of the examples), four ways: 'examples' (today), 'examples+descriptions', 'descriptions' (no examples), and
'examples+descriptions+topoi' (with the praxis's later Argument/Theory test). The
descriptions name no motif of the index. Measured: share right, by genre, and on the person's Oct 9 calls (the
Belief/Theory sorting). Resumable; caches in EXP."""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402

OUT = os.path.join(harness.EXP, 'g1_genre_descriptions.json')
WAYS = ['examples', 'examples+descriptions', 'descriptions', 'examples+descriptions+topoi']

DESCRIPTIONS = {
    'Archetypes': 'a kind of person tellers portray (ethos): "a [type of person] who..."; also a portrait drawn through '
                  'one figure\'s habit',
    'Plots': 'what happened: an event or a sequence of events (mythos): "X happens, then Y"; a plain reading of what '
             'visibly happened stays a Plot, even told with a loaded word',
    'Beliefs': 'a premise people reason from and take for granted (endoxa): common sense, folk wisdom, omens, '
               'nostalgia, prophecy, everyday cynicism; it says what is so, or what a sign means, without saying why, '
               'and names no agent',
    'Theories': 'an account people reason to: the hidden cause, agent or mechanism behind events, which the events '
                'themselves don\'t show (logos, the "because...")',
    'Arguments': 'a rhetorical move people actually make (topoi): "people argue by..."; only when the motif is the move '
                 'itself, a charge or a way of answering',
    'Values': 'how things ought to be: "X should be..."',
    'Exhortations': 'a call to act: "we should do X"',
}
TESTS = """Telling close genres apart:
- Plot or Theory: does the motif add a cause or agent the events don't show? Then a Theory; a plain reading of what \
happened is a Plot.
- Belief or Theory: a Belief is the premise or feeling with no agent; a Theory supplies the agent or mechanism. A \
theory people assume in passing reads as a Belief; one they argue for is a Theory.
- Argument or Archetype: a charge about a pattern of behaviour is an Argument; a portrait of someone's character is \
an Archetype."""
TOPOI = """- Argument or Theory: an Argument is a form of reasoning any side can fill and turn \
around, answered with "that doesn't follow" or "that's beside the point"; its note says someone argues by... so.... A \
Theory is a claim about how the world works, belonging to one picture of it, answered with evidence; its note says X \
happens because Y."""

PROMPT = """Our index of recurring rumor and narrative shapes (motifs) sorts each motif into a genre: what kind of \
thing it is, not its topic. The genres:
{genres}
{tests}
A motif with no genre yet:
{motif}

Which genre is it? If none fits clearly, say none.

reason: a sentence
genre: one of the genres, or none"""


def listing(way: str, examples: dict) -> tuple[str, str]:
    if way == 'examples':
        return '', ''
    rows = []
    for g in DESCRIPTIONS:
        if g not in examples and way != 'descriptions':
            continue
        rows.append(f'{g}: {DESCRIPTIONS[g]}' + ('' if way == 'descriptions' else ', for example:\n'
                    + '\n'.join(f'  - {mi.described(x)[:200]}' for x in examples.get(g, []))))
    return '\n'.join(rows), '\n' + TESTS + ('\n' + TOPOI if way.endswith('topoi') else '') + '\n'


def ask(e: dict, way: str, index: dict) -> dict | None:
    examples = mp.genre_examples(index, leave_out=e['id'])
    if way == 'examples':
        got = mp.ask_genre(e, examples)
        return {'genre': got[0], 'reason': got[1]} if got else None
    genres, tests = listing(way, examples)
    names = list(DESCRIPTIONS)
    schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                               "genre": {"type": "string", "enum": names + ['none']}},
              "required": ["reason", "genre"]}
    a = llm.complete_json(PROMPT.format(genres=genres, tests=tests, motif=mp.shown(e)), schema, max_tokens=400,
                          model=mp.MODEL)
    return {'genre': a['genre'] if a and a.get('genre') in names else None, 'reason': a.get('reason', '')} if a else None


def oct9_calls() -> set[str]:
    """The motifs the person gave a genre on Oct 9 (the Belief/Theory and Plot/Theory sorting)"""
    out = set()
    for r in fc.log_rows():
        if not str(r.get('at', '')).startswith('2026-10-09'):
            continue
        a = r.get('action') or {}
        for s in ([a] + (a.get('steps') or [])) if isinstance(a, dict) else []:
            if isinstance(s, dict) and s.get('action') == 'facet' and s.get('facet') == 'genre' and s.get('value'):
                out.add(s.get('id'))
    return out


def main():
    index = mi.load()
    saved = json.load(open(OUT)) if os.path.exists(OUT) else {}
    motifs = [e for e in mi.live(index) if mi.person_genre(e) in DESCRIPTIONS and e['claims']]
    print(f'{len(motifs)} motifs with the person\'s genre: {dict(Counter(mi.person_genre(e) for e in motifs))}', flush=True)
    for way in WAYS:
        got = saved.setdefault(way, {})
        todo = [e for e in motifs if e['id'] not in got]
        for s in range(0, len(todo), 32):
            part = todo[s:s + 32]
            for e, a in zip(part, llm.parallel(lambda e, way=way: ask(e, way, index), part)):
                if a:
                    got[e['id']] = a
            json.dump(saved, open(OUT, 'w'))
            print(f'{way}: {len(got)}/{len(motifs)}', flush=True)
    truth = {e['id']: mi.person_genre(e) for e in motifs}
    oct9 = oct9_calls() & set(truth)
    lines = [f'G1 genre descriptions, {len(truth)} motifs with the person\'s genre ({len(oct9)} given on Oct 9):']
    for way in WAYS:
        got = saved[way]
        ids = [i for i in truth if i in got]
        right = lambda xs, got=got: sum(got[i]['genre'] == truth[i] for i in xs) / max(len(xs), 1)  # noqa: E731
        o9 = [i for i in ids if i in oct9]
        conf = Counter((truth[i], got[i]['genre']) for i in ids if got[i]['genre'] != truth[i])
        lines.append(f'  {way}: right {right(ids):.1%} (n {len(ids)}), Oct 9 calls {right(o9):.1%} (n {len(o9)}); '
                     f'"none" {sum(got[i]["genre"] is None for i in ids)}; most confused: '
                     + ', '.join(f'{a}->{b} {n}' for (a, b), n in conf.most_common(4)))
        lines.append('    by genre: ' + ', '.join(
            f'{g} {right([i for i in ids if truth[i] == g]):.0%}' for g in DESCRIPTIONS if any(truth[i] == g for i in ids)))
    for ln in lines:
        print(ln, flush=True)
        harness.note(ln)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
