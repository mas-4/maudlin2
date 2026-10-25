"""How a claim is worded, for every model that writes one (Oct 12, Cordelia): posts (narratives.PROMPT), shows
(show_claims.PROMPT), the Focus Group (focus_group.PROMPT) and fact-checks (factchecks.LABEL_PROMPT).

The Brothers Grimm (Oct 9-10, scripts/experiments/w1_claim_wording.py) rewrote 74 of the person's corrected claims
from their sources: Gemma wrote closest to the person's wording (0.784 alike, against 0.758 its current way; the one
way the blind judge preferred to the current one) with three things added after each source's own instruction: the
rules read from the person's corrections (RULES), one short plain sentence (SHORT), and up to EXAMPLES of the person's
corrections of claims from the same kind of source. The text of both rules is the experiment's own, unchanged. Until
Oct 12 none of it was in production (fact-checks had the five latest corrections of any source as examples).

One rule changed since (Oct 25, the person's standing rule): the experiment's "When the tellers disagree, word the
argument itself" gave claims such as "Arguments exist over whether X or Y", ~23 from posts and 2 from shows by Oct 25,
and such a claim pulls in motifs from both sides. A dispute is a telling with one claim per side (the claim praxis,
Oct 12), so the rule now asks for one side's assertion in its own voice, and the claim organizer splits any left
(claim_organizer.disputed)."""
import time

RULES = """How a person who curates these claims rewords them (follow it):
- Word what the tellers claim, never a fact-checker's verdict: "A video shows soldiers looting a church", not "A video \
of looting soldiers is from a film".
- Keep the part that makes it a story: the teller's "because", the charge, the consequence, the whole list ("...and \
nobody was punished", "...because the governor owed them a favor").
- Keep the teller's own strength and framing; don't soften it into a neutral paraphrase ("The banks are robbing \
ordinary savers", not "Banks offer low interest rates").
- Add nothing the tellers don't say: no motive, threat or framing of your own (if a mayor says he's disappointed in a newspaper, \
don't write that he threatened it).
- A claim is one side's assertion in that side's own voice: when the tellers disagree, each side's claim is its own, \
and two sides make two claims. Never word a claim as a sentence about the dispute ("Arguments exist over whether...", \
"Debates persist over...", "There is debate over..." are not claims).
- Allegations against people stay allegations: "accused", "critics say", "is said to"; never state a crime as fact. \
Name lesser-known people by their role ("a city councilman", "the plaintiff", "a former aide").
- If the claim says who says it, get it right: a guest, a host or a clip is not "the voter"; an aide is not the \
president.
- Spell names of people and organizations as they're usually written (transcripts mishear them), and give full names.
- Exact facts from the source: who sued whom, the amounts, the place.
- A stated concern is worded as the belief behind it ("elections should be paid for by citizens, not corporations", \
not "corporate money is a big issue")."""

SHORT = """- Write it as the person does: one short, plain sentence, usually under 20 words, saying what is claimed, not \
who reports it or where it circulates ("A video shows a crowd storming a stadium", not "Social media posts claim a \
video shows a crowd storming a stadium"); leave out dates, places and numbers unless the claim turns on them."""

EXAMPLES = 8  # of the person's corrections of claims from the same kind of source
KINDS = ('posts', 'shows', 'Focus Group', 'fact-checks')
KEEP = 600  # seconds the examples are kept between prompts (a run writes many claims; the index is big)
_memo = {}


def kind_of(source: str) -> str:
    """The kind of source a claim's `source` names: anything not posts, shows or the Focus Group is a fact-checker"""
    return {'narrative': 'posts', 'shows': 'shows', 'Focus Group': 'Focus Group'}.get(source, 'fact-checks')


def authors() -> dict[tuple[str, str], int]:
    """Who made each logged correction (the claim's words, the new words) -> 0 the person, 1 Claude with the person's
    approval noted, 2 Claude alone (a curation session can't steer the claim writer by accident: the curation session's
    note, Oct 12, after ~20 of its long "Posters say..." corrections reached the examples)"""
    from app.analysis import curation_db
    out = {}
    try:
        rows = curation_db.actions()
    except Exception:  # noqa: BLE001 - no log: every correction counts as the person's
        return out
    for r in rows:
        a, by = r['action'], (r.get('by') or '')
        rank = 0 if not by else 1 if 'approved' in by else 2
        for step in (a.get('steps') or []) if a.get('action') == 'batch' else [a]:
            if isinstance(step, dict) and step.get('action') == 'correct':
                out[(step.get('claim', ''), step.get('text', ''))] = rank
    return out


def examples(kind: str, index: dict | None = None, n: int = EXAMPLES) -> str:
    """The person's latest corrections (✎) of claims from this kind of source, as the Brothers Grimm showed them: the
    ones they typed first, then Claude's they approved, then Claude's alone only to fill the n"""
    from app.analysis import motif_index as mi
    index = index if index is not None else mi.load()
    source = {mi.key(c['claim']): c.get('source', '') for e in index.get('entries', {}).values() for c in e.get('claims', [])}
    fixes = [(a, b) for a, b in index.get('corrections', {}).items()
             if a != b and len(a) < 400 and len(b) < 400 and mi.key(b) in source and kind_of(source[mi.key(b)]) == kind]
    by = authors()
    order = {fix: i for i, fix in enumerate(fixes)}  # the index keeps them oldest first
    fixes = sorted(fixes, key=lambda f: (by.get(f, 0), -order[f]))[:n][::-1]  # the best n, then oldest first as before
    if not fixes:
        return ''
    return ('\nHow the person corrected claims from the same kind of source before (do as they did):\n'
            + '\n'.join(f'- "{a}" became "{b}"' for a, b in fixes))


def rules(kind: str, index: dict | None = None) -> str:
    """What goes after a source's own instruction for its claim: the rules, the short rule, the person's examples"""
    if index is None and kind in _memo and time.time() - _memo[kind][0] < KEEP:
        return _memo[kind][1]
    try:
        shown = examples(kind, index)
    except Exception:  # noqa: BLE001 - an unreadable index: the rules without examples
        shown = ''
    text = '\n' + RULES + '\n' + SHORT + shown
    if index is None:
        _memo[kind] = (time.time(), text)
    return text
