# Motif praxis: how claims are filed and motifs are shaped

How the person files claims under motifs and shapes the motifs themselves: the working rules, the genres and how to
tell them apart, names, seeds, and how claims are worded. Written Oct 9, 2026 from the person's sessions of Oct 8–9
(first in chat, then with Claude through the maudlin MCP). It is the reference for anyone, person or model, proposing a
filing, a motif, a note or a genre, and material for the models to refine on; the worked examples behind each rule are
in `docs/motif-casebook.md`. The rules are practice written down, not a codebook laid down in advance: the index is
built bottom-up, and this records what the building has taught.

The index reads claims for their **shape, not their truth**: a motif is a recurring way of telling, and a false claim
and a true one can share it.

## Working rules

1. **Cite.** Every proposed filing quotes the teller's words that carry it: a post, a transcript line, a fact-check's
   summary of what was claimed. A filing nobody's words carry is a guess.
2. **Note, genre, groups.** A new motif comes with all three, and so does an existing one being applied for the first
   time without them.
3. **Repetition bar.** A new motif normally needs two independent tellers (distinct posters or shows; one host across
   several segments counts once). An existing motif can be applied on one telling.
4. **Outside life.** A motif with a long life outside the corpus (a proverb, a famous phrase, a folklore type) can enter
   on one telling. Say that the exception is used.
5. **Sparing.** Lead with existing motifs; at most one or two new ones per claim.
6. **Shapes, not spread.** Fact-check mechanics (fake branding, deepfakes, clipped video, wrong counts, misleading
   headlines) are not motifs. Breaking-news framing alone doesn't earn one.
7. **File the telling, not the why.** File what the tellers say, never a reading of why the story is circulating
   (Oct 9). A straight news telling ("Trump has a call scheduled with Putin") gets no motif even when its obvious subtext
   is why it travels, unless a teller voices that subtext. Don't put a critic's verdict on a teller who didn't make it:
   Bribing voters needs someone calling it a bribe. Hate tropes apply only when a teller invokes them. Why a story
   spreads belongs to the flow layer (which shows pick it up, what it travels with), not to the filing.
8. **Fix the claim.** A claim's words should carry what its tellings say. Reword a gloss that takes a side or the
   fact-check's verdict; word a debate as the argument it is; check who said it (focus-group and radio quotes are often
   the host or a played clip). When a gloss hides the part a motif is filed for, reword it from the posts and
   transcripts (the ADHD claim's one "victim blames them" post, Oct 9).
9. **Real people.** Word allegations to what the tellings establish: "accused", "says", "is said to".
10. **No side labels in claims.** Don't name the tellers' politics in the claim; the source panel carries that, unless
    the claim depends on who said it.
11. **No motif is fine.** Anodyne news gets none rather than a forced one.
12. **One claim, two sides, stays one claim.** When both sides tell the same subject (both camps in Brazil say they're
    censored), reword the claim to carry both rather than splitting it. A split is for two different subjects merged by
    the clustering (Democrats angry at their own leaders, merged into an anti-incumbent claim).

## Genres

Every motif has one genre: what kind of thing it is, not its topic. Rests-on links may cross genres.

**These definitions are found, not given.** The genres began as names with a rough verb test and no definitions; the
person has been sorting motifs into them case by case and letting the categories show themselves, the Aristotelian
way: from the particulars and what people already say about them (endoxa) toward the definition. What follows is what
the sorting has shown so far (Oct 9), drawn from the cases in `docs/motif-casebook.md`. It is provisional: when a case
doesn't fit, the case wins and the definition is revised. The verb test was a starting point; the person found it has
"a decent amount of problems". The genre-drafting model (`motif_proposals.GENRE_PROMPT`) still sees only examples of
each genre, no definitions; giving it these is a later step, once they settle, measured against the person's own
genre calls.

| Genre | What it is | Aristotle | Quick test |
|---|---|---|---|
| **Archetypes** | a kind of person tellers portray | ethos | "a [type of person] who…" |
| **Plots** | what happened: an event or sequence | mythos | "X happens, then Y" |
| **Beliefs** | a premise people reason *from* | endoxa | what comes before "so…" |
| **Theories** | an account people reason *to*: a cause, agent or mechanism | logos (giving the *aitia*) | the "because…" |
| **Arguments** | a rhetorical move people actually make | topoi | "people argue by…" |
| **Values** | how things ought to be | — | "X should be…" |
| **Exhortations** | a call to act | protropē | "we should do X" |

### Plot or Theory

"The plot is what happened, the motif is what people think about it" (the person, Oct 9), refined the same day: a
Theory reaches **below the surface** for a hidden cause, agent or mechanism the event itself doesn't show. A plain
reading of what visibly happened stays a Plot, even with a loaded word.

- Plot: Bribing voters. "$5,000 checks if Republicans win" is vote-buying on its face.
- Theory: It was one of them. A plain crash, and people say "it was one of them!": a hidden agent, added.
- Plot: Graft (the particular deal handed to a donor). Theory: Corruption (officials enrich themselves: how power
  works).
- Plot: Proxy warfare. Its tellings are episodes ("Iran-backed Houthis", "Saudi-backed forces"), told as moves between
  patrons; nobody theorizes proxy war as such.

A model can apply this as one question: *does the motif add a cause or agent the event doesn't show?*

### Belief or Theory

A **Belief** is what people take for granted and reason from: common sense, folk wisdom, omens, nostalgia, prophecy,
everyday cynicism. It says what is so, or what a sign means, without saying why. A **Theory** names the cause, agent or
mechanism. Pairs already in the index show the line:

| Belief (the premise, the feeling) | Theory (the explanation) |
|---|---|
| Polls are inaccurate | Polls are manipulated |
| Something feels off | Conspiracy |
| Wasted vote | Broken electoral math |
| It's quiet, too quiet | Elite cabal |

In each pair the Belief has no agent; the Theory supplies one. Moved to Beliefs on Oct 9: Polls are inaccurate,
Politicians' empty promises, Political theater, End times, In this economy?. Moved the other way: Cancel culture (a
diagnosis of how society works). AI is existentially dangerous stays a Theory: an argued causal account (uncontrolled
AI turns on us), not a premise like End times.

Blurry edge: a widely shared theory used in passing reads as a belief ("money buys politicians"). File by how the
tellers use it: argued for, a Theory; assumed, a Belief.

### Argument, Archetype or Plot

- **Arguments** only when the motif is the move itself. Blame the victim is the *charge* "you're blaming the victim";
  the doubters' own tellings ("she only decided she was assaulted after she was disinvited") are a different shape,
  Potiphar's wife.
- **Archetypes** when tellers portray a kind of person, even through one figure's habit: Passing the buck ("his zone is
  blame"), Narcissus (rages when the admiration stops).
- A motif told as a charge about a pattern is an Argument; told as a portrait of someone's character, an Archetype.

## Notes

A note says the shape in one or two sentences, in the genre's own form (an Archetype's note describes the person, a
Plot's the sequence). Widen a note when its claims outgrow it (Some of you may die now covers any group keeping its
benefits while others pay); narrow it when it hides two motifs (Reward a loyal political figure, the Value, split from
It's her turn, the Theory).

## Names

The person likes classical and literary names (Caligula, Tommy, Mors omnia solvit, Potiphar's wife, Lucretia,
Narcissus) but takes a plain one when it reads better or the classical one is obscure: "if a name just feels like Latin
for no really good reason I make it simpler". Plain names may also help the filing models match. Prefer a known idiom
(Throw the bums out, Passing the buck, Pain at the pump, He said, she said, Shadowbanned).

## Seeds

A motif idea with one telling or none is created at once as a motif with no claims (the checker's `add`), with its
note, genre and groups (Oct 9: "there's no reason not to, it would help with the claim system"). The filing models can
then find it when the next telling comes. The repetition bar governs how sure a filing is, not whether the motif exists.

## Hierarchy

Rests-on is the only hierarchy: a motif rests on another when it only makes sense given it (a kind of it, or a case,
argument or figure that tells it), across genres too. Everything else is "related". Co-occurrence is not relatedness:
motifs told together aren't thereby related. Examples: Potiphar's wife rests on He said, she said; Pain at the pump on
In this economy?; In this economy? on It's the economy, stupid.

## Decisions teach the models

Every change goes through the checker and into the curation log. The confidence model and the reranker learn from the
person's verdicts there (✓ fits, ✕ take out, moves, hand filings). Changes Claude carries out on the person's word,
through the MCP, are marked "by Claude" in the log and count as the person's (Oct 9: "I'm making decisions here and
these are correct decisions"). Notes, genres, groups, names and claim rewordings go into the index as the person's.
