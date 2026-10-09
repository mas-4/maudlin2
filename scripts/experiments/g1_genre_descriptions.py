"""G1 genre descriptions (Oct 9). The genre drafter (motif_proposals.GENRE_PROMPT, Gemma 4 26B) sees each genre only as
five of the person's motifs in it. docs/motif-praxis.md now says what each genre is, as the person's sorting has shown
it, with the Plot/Theory, Belief/Theory and Argument/Archetype tests; it says to give the drafter these once they
settle, measured against the person's own genre calls. Here every motif the person gave a genre is asked again (left
out of the examples), four ways: 'examples' (today), 'examples+descriptions', 'descriptions' (no examples), and
'examples+descriptions+topoi' (with the praxis's later Argument/Theory test), and 'refined' (the praxis's lines as
refined after this experiment's own split report, with Perennials, a genre added Oct 9), and 'refined2' (refined, with
the Plot/Theory line drawn again after 'refined' overshot toward Plot: observed situations and established exposés
are Plots; explained situations and hints pieced together are Theories). Note: the person moved some
genres after that report, so 'refined' is scored partly on calls made in view of it. The
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
WAYS = ['examples', 'examples+descriptions', 'descriptions', 'examples+descriptions+topoi', 'refined', 'refined2']

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
    'Perennials': 'a safe topic shared for its own sake, which strangers can talk about without taking a side (the '
                  'weather, babies, pets, sports, birds); the one genre defined by its subject; never politics',
}
# The praxis's lines as refined after the drafter's split report (Oct 9, later): 'refined' asks with these
REFINED = {
    'Archetypes': 'a kind of person tellers portray (ethos): "the [type of person] who..."; an epithet that labels a '
                  'kind of person is an Archetype',
    'Plots': 'what happened or is happening (mythos): an event, a sequence, a standing situation or a decline; an '
             'exposé, where hidden wrongdoing comes out, is a Plot; so is a plain reading of what visibly happened, '
             'even told with a loaded word',
    'Beliefs': 'a premise or lore people pass on and take for granted (endoxa): common sense, folk wisdom, omens, '
               'scares, nostalgia, prophecy, everyday cynicism; reasoned from, not argued for',
    'Theories': 'an account people argue about how the world or society works, often a hidden cause, agent or '
                'mechanism the teller infers rather than sees revealed (logos, the "because..."); naming an agent is a '
                'sign, not the definition',
    'Arguments': 'a rhetorical move people make in a debate (topoi): a charge about someone\'s conduct, a way of '
                 'answering, or a teller offering proof; about the debate rather than the world',
    'Values': 'how things ought to be: "X should be...", including what someone deserves or has no business doing',
    'Exhortations': 'a call to act: "we should do X"',
    'Perennials': DESCRIPTIONS['Perennials'],
}
TESTS = """Telling close genres apart:
- Plot or Theory: does the motif add a cause or agent the events don't show? Then a Theory; a plain reading of what \
happened is a Plot.
- Belief or Theory: a Belief is the premise or feeling with no agent; a Theory supplies the agent or mechanism. A \
theory people assume in passing reads as a Belief; one they argue for is a Theory.
- Argument or Archetype: a charge about a pattern of behaviour is an Argument; a portrait of someone's character is \
an Archetype."""
REFINED_TESTS = """Telling close genres apart:
- Plot or Theory: is the hidden hand revealed in the telling (an exposé: a Plot) or inferred by the teller (an \
alleged hidden cause or agent: a Theory)? Backers named openly hide nothing: a Plot.
- Belief or Theory: an argued account of how society works is a Theory, even with no agent named; lore or a premise \
people pass on is a Belief, even if it names a cause. A judgment of how things ought to be is a Value.
- Argument or Theory: is the motif about the debate (a form of reasoning any side could use) or about the world (what \
happens and why)?
- Argument or Archetype: an epithet labelling a kind of person is an Archetype; a charge about conduct is an Argument.
- Argument or Plot: a teller offering proof is an Argument; a recurring situation in which the truth is contested or \
comes out is a Plot.
- Archetype or Plot: a motif described around a figure is an Archetype; around an incident, a Plot."""
# 'refined' overshot toward Plot (Theories 73% -> 51%): it took explained situations and alleged revelations for Plots
REFINED2 = dict(REFINED, **{
    'Plots': 'what happened or is happening (mythos): an event, a sequence, a decline, or a standing situation people '
             'observe (a price, a shortage); an established exposé, where a document, an admission or an investigation '
             'brings hidden wrongdoing out, is a Plot; so is a plain reading of what visibly happened, even told with '
             'a loaded word',
    'Theories': 'an account people argue about how the world or society works (logos, the "because..."): a hidden cause, '
                'agent or mechanism the teller infers, or an explanation of what drives an ongoing situation (why the '
                'country is split, how insiders protect each other); tellers piecing hints together to claim a hidden '
                'hand is a Theory, however much the telling speaks of revealing; naming an agent is a sign, not the '
                'definition',
})
REFINED2_TESTS = REFINED_TESTS.replace("""- Plot or Theory: is the hidden hand revealed in the telling (an exposé: a Plot) or inferred by the teller (an \
alleged hidden cause or agent: a Theory)? Backers named openly hide nothing: a Plot.""", """- Plot or Theory: is the hidden hand established (a document came out, someone admitted it, an investigation found \
it: a Plot) or pieced together by the tellers from hints (a Theory)? Would it still be there without the tellers' \
inference? Backers named openly hide nothing: a Plot. A standing situation people observe (the price, the shortage) \
is a Plot; an account of what drives one is a Theory: is the motif the condition itself, or an explanation of it?""")
assert REFINED2_TESTS != REFINED_TESTS
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
    said = {'refined': REFINED, 'refined2': REFINED2}.get(way, DESCRIPTIONS)
    for g in DESCRIPTIONS:
        if g not in examples and way != 'descriptions':
            continue
        rows.append(f'{g}: {said[g]}' + ('' if way == 'descriptions' else ', for example:\n'
                    + '\n'.join(f'  - {mi.described(x)[:200]}' for x in examples.get(g, []))))
    if way.startswith('refined'):
        return '\n'.join(rows), '\n' + (REFINED2_TESTS if way == 'refined2' else REFINED_TESTS) + '\n'
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
