# Filing experiments

A lab notebook for the project's first priority since Oct 8: filing claims under the right motifs, so the person checks
less and the model misses less. Each entry: the idea, how it was tested, the numbers, and what was kept. Scripts are
in `scripts/experiments/`; their data (cached signals, model answers) in `maudlin-data/motifs/experiments/`.

## How things are measured

Everything is tested on the person's own judgments, each claim held out (grouped folds: no claim is ever scored by a
model that saw it, and it's taken out of its own motifs first, so a claim already filed is tested as if new).

- **Finding** (recall): of the person's confirmed filings (891 on Oct 8), how many land in a finder's top 8 / 12 / 20 /
  40 motifs. Top 12 is about what the filing model sees. The **hard misses** are filings outside the top 40 (73 on Oct 8,
  47 of them the person's own hand-adds): the structural readings ("the PQ's comeback" as *Phoenix from the ashes*).
- **Sorting** (confidence): of the person's keep/remove decisions on the model's filings (749: 592 kept, 157 removed),
  AUC, and how many kept filings can be passed at 95% precision ("sure").
- **Picking** (the filing model's choice among the shortlist): of a sample of the person's confirmed claims, how many of
  their motifs it picks, and how many of its picks aren't theirs.

`scripts/experiments/harness.py` scores any new finding signal the same way (`evaluate(data, extra={...})`).

Experiments that need the GPU run under the GPU lease (`app/gpu_lease.py`, Oct 9): `python -m app.gpu_lease run
--minutes 45 -- .venv/bin/python -u scripts/experiments/x.py` waits for the hourly run to be over, then holds the lease
while the script runs; the always-on worker finishes its current step and waits until it's given back (or runs out).

## Where things stood on the morning of Oct 8

- Finding: today's shortlist (six likenesses from one embedder, weighed by a logistic regression) put 75.0% of the
  person's motifs in its top 8, 79.6% in the top 12.
- Sorting: the confidence model (the same likenesses) AUC 0.82; it plateaued at about 150 decisions (more checking
  wouldn't help: it only knew how alike things look).
- Picking: Gemma (gemma4:26b), side by side among the shortlist, found 66% of the person's motifs in it, 26% of its
  picks not theirs.

## Done

### E0.1 Gemma's own yes or no, with its probability (Oct 8) — kept
Each decided pair put to Gemma alone ("is this claim an instance of this motif?", the motif's name, note and its three
claims nearest this one), P(yes) from the answer token's log-probabilities.
- Alone: AUC 0.818, but overconfident (precision flat at ~91% from P 0.5 to 0.99).
- With the likenesses: AUC 0.817 → **0.879**; kept filings passable at 95% precision 29% → 64%. They're wrong about
  different filings.

### E0.2 A cross-encoder reranker, off the shelf (Oct 8) — kept
Qwen3-Reranker-0.6B (CPU), reading the claim with the motif's note and two nearest claims.
- Alone AUC 0.766; with the likenesses 0.852; with the likenesses and Gemma **0.887**.
- Not yet trained on the person's decisions (E9).

### E0.3 The note alone in the shortlist (Oct 8) — small
The person: the names are playful nicknames; the note says what a motif covers. The claim against the note alone as a
seventh likeness: top 8 73.9% → 75.0%, top 12 unchanged (79.3%). The note was already read, glued to the name.

### E0.4 A note-first picking prompt (Oct 8) — not kept
Each motif shown by its note ("nicknamed …"), the name called a nickname, with its three claims nearest this one rather
than its latest three; 120 confirmed claims: found 57% of the person's motifs (today 66%), 21% of picks not theirs
(today 26%). More cautious, missing more than it saves. Two changes at once: the nearest-claims half to be tried alone
(E8).

### E0.5 Many finders (Oct 8) — kept, weighted
Signals in `app/analysis/motif_signals.py`, each alone, then weighted on the person's filings (top 8 / 12 / 20 / 40):

| finder | top 8 | top 12 | top 20 | top 40 |
|---|---|---|---|---|
| today's shortlist | 75.0 | 79.6 | 85.4 | 90.2 |
| note alone | 57.5 | 62.9 | 69.6 | 79.0 |
| keywords (BM25 over note, name, claims) | 53.6 | 57.9 | 62.5 | 69.2 |
| shape (Gemma's bare rewrite) against notes | 51.3 | 57.5 | 66.9 | 76.4 |
| votes of the nearest filed claims | 47.0 | 51.1 | 55.9 | 59.0 |
| nomic-embed-text (a second embedder) | 44.4 | 50.2 | 56.1 | 65.9 |
| group route (the claim against its best group) | 12.5 | 16.5 | 22.4 | 32.7 |
| all, fused unweighted (reciprocal rank) | 63.3 | 72.3 | 81.8 | 89.1 |
| **all, weighted on the person's filings** | **77.2** | **82.5** | **86.6** | **91.8** |

None alone beats today's (already a weighted blend); weighted together they add ~3 points at 12. Unweighted fusion
hurts. The group route is weak alone (43% of motifs are grouped, and a group is coarse) but enters the weighting.

### E0.6 The confidence model on every signal (Oct 8) — kept, live
Likenesses + the new finders + reranker + Gemma's yes/no, a logistic regression on 749 decisions: **AUC 0.885**; at a fit
of 85%, 76% of kept filings pass at 95.1% precision. Training with the person's 219 hand-adds as extra positives: no
change (0.883). Boosted trees (they can learn when to trust which signal) did no better, and both level off by half the
decisions:

| share of decisions | logistic AUC | trees AUC |
|---|---|---|
| 25% | 0.853 | 0.816 |
| 50% | 0.867 | 0.890 |
| 75% | 0.895 | 0.891 |
| 100% | 0.891 | 0.859 |

So more checking alone won't move it much; new kinds of evidence will. Live from Oct 8 midday: fits worked out in the
hourly run and kept on the filings; the check list goes likeliest first; the sure ones in a fold to look over; a second
look at the model's confirmed filings it now doubts.

### E3 Motifs travel in bundles (Oct 8) — small
`scripts/experiments/e3_e5_bundles_graph.py`. The person's filings counted in pairs (the claim scored left out of the
counts); a held-out claim's anchors are its top 3 motifs by today's shortlist; every other motif scored by how often
it's filed with them. Against the weighted finders (top 12 82.3%, 76 hard misses on the rebuilt signals):
top 12 82.9%, 73 misses (5 back, 2 new). A little, mostly on a claim's later motifs. Kept as a candidate signal.

### E5 Spread over the person's links (Oct 8) — promising, unproven; testing forward
`e3_e5_bundles_graph.py`, `e5_variants.py`, `e5_temporal.py`. Each motif scored by its best neighbour's score through
the person's rests-on and related links:

| variant | top 8 | top 12 | top 40 | hard misses |
|---|---|---|---|---|
| baseline | 77.7 | 82.3 | 91.5 | 76 |
| rests-on and related, best neighbour | 79.3 | **84.7** | 92.8 | 64 |
| related only | 79.3 | 83.5 | 92.8 | 64 |
| rests-on only | 78.3 | 83.4 | 92.1 | 70 |
| both, two hops | 79.0 | 84.6 | 93.2 | 61 |
| both, mean of neighbours | 78.7 | 83.1 | 92.9 | 63 |
| group mates | 77.3 | 81.7 | 91.5 | 76 |
| links made before the claim came in (strict) | 77.6 | 82.5 | 91.7 | 74 |

The best gain of the day, but it may be partly the links echoing claims already filed together (until Oct 7 the
proposer suggested links from shared claims): kept only to links made before each claim, it vanishes. That test is
weak (the claims date from Oct 2–7, nearly all 330 links were made Oct 5–8, so most claims see almost none), so the
verdict waits for a forward test: what it would suggest for new claims, scored against the person's checks.
Forward test from Oct 8 afternoon (`e5_forward.py`): each new claim nobody has said yes to yet is ranked against
every motif twice, by the learned weighting with and without the spread (the links as they stand then, the claim held
out of the motifs the model put it in), the top 40 of each logged; `score` compares them on the claims the person has
checked since. Logged in each GPU window as claims come in.

### E1 Subtract the news (Oct 8) — kept: in production
`scripts/experiments/e1_news.py`. The 6,000 most recent headlines embedded (mxbai); their top principal components
(the directions the day's news varies along: mostly topic) projected out of the claim, the motif notes and the motifs'
claims; then the claim against each note and its nearest claim (held out) in what's left, two signals added to the
weighting:

| topic directions out | top 8 | top 12 | top 40 | hard misses |
|---|---|---|---|---|
| none (baseline) | 77.7 | 82.3 | 91.5 | 76 |
| 5 | 78.2 | 83.6 | 92.0 | 71 |
| 10 | 77.8 | 83.1 | 92.1 | 70 |
| 20 | 77.9 | 83.2 | 91.9 | 72 |
| 40 | 78.0 | **83.6** | **92.4** | **68** (11 back, 3 new) |

A steady point at 12 whatever the number, and the most hard misses back at 40. Smaller than E5's gain but with no
question of leakage (the headlines know nothing of the person's filings), and cheap: the components once a day, a
projection per comparison. In production the same afternoon (motif_signals.py, 'news out note' and 'news out near',
40 directions), a signal of the filing confidence model from its next retrain. Retrained (14:32, 753 decisions): AUC
0.882; with and without the two signals on the same pairs, 0.882 and 0.883, the same sure line (90%) and 66% of kept
filings passable at 95% precision either way. So it helps find the person's motifs (the shortlist's recall), not
judge a filing once found: its gain waits for the learned shortlist in production. (The 76% of the morning fell to
66% with the day's new decisions and edits, not the signal: the 95% line is a coarse step.)

### E2 Imagined instances and E7 The layered finder (Oct 8) — E2 nothing; E7 kept
`scripts/experiments/e2_e7_imagined_layers.py` (gemma4:26b's answers cached in maudlin-data/motifs/experiments).
E2: for each motif, eight claims people might tell that are instances of it, each on a different subject, written from
its name and note only (never its claims); a claim scored by its best and mean match among them. E7: each claim
described layer by layer in plain generic words (a character type, a plot, a theory or belief, an argument, a value at
stake; "none" where it has none), each layer against every motif's note, and separately the layer that goes with the
motif's genre (Archetypes: character; Plots: plot; Theories and Beliefs: theory; Arguments: argument; Values and
Exhortations: value).

| variant | top 8 | top 12 | top 40 | hard misses |
|---|---|---|---|---|
| baseline | 77.7 | 82.3 | 91.5 | 76 |
| E2 imagined instances | 78.0 | 82.5 | 91.7 | 74 (6 back, 4 new) |
| **E7 layered finder** | **79.7** | **83.7** | **92.5** | **67** (17 back, 8 new) |
| E2 and E7 together | 79.6 | 84.1 | 92.4 | 68 |

E7 is the day's best gain with nothing of the person's filings in it to leak: reading a claim as the stack of stories
it tells (who it's about, what happens, what's believed to cause it, what it argues, what's at stake) and matching
each layer to motifs of that layer is how the person reads them. The imagined instances add nearly nothing over the
notes they were written from. Next: E7's two signals into motif_signals (the layers asked of the filing model once per
new claim, cached) and the combiner retrained.

### E1b The news of the claims' own time (Oct 8) — no better (on thin history)
`scripts/experiments/e1b_news_span.py`. The person asked whether the old claims had been de-newsed too. They had (E1
takes the directions out of both sides), but with the wrong news: "the latest 6,000 headlines" by last_accessed are a
single snapshot of today's front pages (all 6,000 from the last three minutes; a headline's last_accessed moves while
it stays up), while the claims filed go back to July (17 in July, 94 in August, 134 in September, 735 in October). Here
the directions come from 120 headlines from each day since the earliest claim, by the day each was first seen, against
today's snapshot, 40 and 80 directions out. Production (motif_signals.latest_headlines) has the same snapshot and
follows the verdict.

Result: no different. With 40 directions out, the snapshot 83.7% and the whole span 83.6% (hard misses 69 and 68);
with 80, 83.7% and 83.2%. But the database gave only 840 headlines by the day they were first seen since July 18 (120
a day on seven days), so the whole span was mostly this week anyway: the headline table keeps little history. Left as
it is until there's more history to test on.

### E9 The reranker taught the person's taste (Oct 8) — in production (app/analysis/reranker_teach.py)
`scripts/experiments/e9_reranker_tune.py`. Qwen3-Reranker-0.6B's top 6 of 28 layers (94M of 596M weights) trained on
2,311 pairs: the person's 752 decisions on the model's filings (591 kept, 161 removed), their confirmed claims' other
motifs (314), and for each confirmed claim the 3 motifs today's shortlist ranks highest that aren't theirs (1,245 hard
negatives). Three folds by claim, two passes each, on the CPU at low priority (the GPU is Gemma's: about 5 s a batch
of 8, under 2 hours in all); each fold tested on the decisions of claims it never saw. Measured: the reranker's AUC
alone on those decisions before and after, and the confidence model's with the taught one in its place.

Result (1 h 40 min on the CPU): the reranker alone, on the 752 decisions of claims each fold never saw, AUC 0.765 ->
**0.796**. In the confidence model (the same 752 pairs, its own folds by claim): 0.887 -> 0.890, and the filings it
can pass at 95% precision 66% -> 76% (the sure line 90% -> 85%); with both rerankers side by side, 0.889 and 66%. The
AUC gain is small and the 95% line is a coarse step, so the 76% is fragile; but the reranker learned something of the
person's reading that the other signals don't carry. To put it in production: train it once on all their decisions,
keep the top layers it changed (94M weights), retrain weekly as decisions grow.

### J1 A jury of models (Oct 8) — Nimble 9B judges as well as Gemma 26B, several times faster

The person: "having multiple models evaluate and work through our claim motif stack". Every filing they had decided
(817: 631 kept, 186 taken out) judged by each juror, is this claim an instance of this motif? Decision models (one
pass, a probability, no text: Ollama's `/v1/systemone`) and language models asked the filing model's yes or no
(P(yes) from the first word's log-probabilities). AUC alone, and the confidence model's held-out AUC (folds by claim)
with that juror as its yes-or-no signal; seconds a filing four at once (Gemma 26B's own from the hourly run, ~1-2 s):

| Juror | Alone | In the confidence model | s a filing |
|---|---|---|---|
| none | | 0.870 | |
| Nimble 9B (Bespoke Labs, decision) | **0.824** | **0.895** | 0.22 |
| Gemma 4 26B (today's) | 0.818 | 0.894 | ~1-2 |
| Tev1 4B (Together AI, decision) | 0.782 | 0.889 | 0.11 |
| Ministral 3 14B | 0.757 | 0.889 | 0.37 |
| Qwen3.5 9B | 0.772 | 0.884 | 0.13 |
| Gemma 4 12B | 0.786 | 0.883 | 0.36 |
| Tev1 0.8B (decision) | 0.687 | 0.870 | 0.04 |
| Laya (ModernBERT-large, decision, on the CPU) | 0.686 | 0.869 | 0.28 |
| all eight | | 0.897 | |
| all but Gemma 26B | | 0.892 | |

Nimble, which fits the card whole, does Gemma 26B's yes-or-no as well; a jury adds little over one good juror
(0.897 against 0.895): what's left is in other kinds of evidence, or in more of the person's decisions. Clef-flash
failed to load at its default context (retried at 8k), Clef 27B and GEV-26B-Decide (Gemma 26B with a decision head,
built for Ollama by `gev_build.py`) to come. `scripts/experiments/j1_jury.py`.

### E11 Every embedder (Oct 9, overnight) — Qwen3-Embedding 8B with Snowflake Arctic 2: top-12 82.3% -> 85.2%

Twelve embedding models from Ollama's library (and EmbeddingGemma 2 from Hugging Face), each giving the shortlist
two signals as mxbai's do (the claim against the motif's name and note, and against its nearest claim, held out),
each with its own query and document prefixes. Top-12 of the person's motifs alone, and added to every signal we have
(the harness: today 82.3%, 76 hard misses outside the top 40):

| Embedder | Alone, top-12 | Added: top-12 | top-8 | top-40 | misses |
|---|---|---|---|---|---|
| mxbai-embed-large (today's) | 65.4% | 82.2% | 78.2% | 91.1% | 79 |
| nomic-embed-text (today's) | 48.8% | 82.6% | 77.8% | 91.6% | 75 |
| nomic-embed-text-v2-moe | 60.7% | 82.4% | 78.1% | 91.8% | 73 |
| embeddinggemma 300m | **70.8%** | 82.5% | 79.5% | 92.0% | 71 |
| embeddinggemma-2 (Hugging Face; v1's prefixes, to check) | 55.2% | 82.5% | 77.6% | 91.6% | 75 |
| qwen3-embedding 0.6b | 58.9% | 82.5% | 78.9% | 92.0% | 71 |
| qwen3-embedding 4b | 62.5% | 84.1% | 79.7% | 93.0% | 62 |
| **qwen3-embedding 8b** | 70.7% | **84.8%** | **80.9%** | **93.5%** | **58** |
| bge-m3 | 56.9% | 82.5% | 78.5% | 91.9% | 72 |
| bge-large | 62.0% | 82.4% | 78.0% | 91.5% | 76 |
| snowflake-arctic-embed2 | 65.8% | 83.3% | 79.6% | 92.8% | 64 |
| granite-embedding 278m | 54.4% | 82.2% | 78.5% | 91.6% | 75 |

Together (from the saved vectors): Qwen3-Embedding 8B + Arctic 2, top-12 **85.2%**, top-8 81.0%, top-40 94.2%, misses
52 (31 brought back); with EmbeddingGemma 300m too, the same; Qwen3 4B + Arctic 2 + EmbeddingGemma, 84.6%; the two
small ones alone, 83.3%. Next: the 8B and Arctic 2 into the learned shortlist (the 8B is 4.7 GB: its own batch, or the
CPU). `scripts/experiments/e11_embedders.py`.

### E4 A jury of readers and E6 Ask what teaches most (Oct 9, overnight) — E4 nothing; E6 least certain first

**E4.** Gemma 4 26B's yes or no on 753 of the person's decided filings as three readers (a folklorist cataloguing
story types the way Thompson indexed motifs, a rhetorician, a reader from the claim's other side), against today's
plain question. Alone: plain 0.820, folklorist 0.794, rhetorician 0.796, other side 0.762, the three's mean 0.807. In
the confidence model in place of the plain question: 0.882 (plain), 0.883, 0.885, 0.870; all three added, 0.886. The
plain question already asks the folklorist's question ("the same shape of story, as its tellers tell it, not just the
same topic, person or word"); the persona adds nothing to it. The folklorist's reading stays where it is: naming and
proposing motifs.

**E6.** The person checking in different orders (simulated on the same decisions, a quarter of the claims held out,
five draws): the held-out AUC after N decisions.

| Order | 50 | 150 | 250 | 350 | 450 | 550 |
|---|---|---|---|---|---|---|
| least certain first | 0.852 | **0.884** | **0.888** | 0.887 | 0.883 | 0.883 |
| random | 0.847 | 0.867 | 0.866 | 0.871 | 0.878 | 0.882 |
| likeliest first (today's check list) | 0.820 | 0.839 | 0.845 | 0.860 | 0.870 | 0.883 |

Least certain first gets in 150 decisions what random order gets in about 550 and the check list's likeliest-first
order later still: the filings the model is sure of teach it least. For the person's limited time, 🎯 today should
serve the uncertain ones first. `scripts/experiments/e4_e6_jury_active.py`.

### C1 A cascade (Oct 9, overnight) — not worth it: Gemma 26B picks with the fewest wrong

The person: run everything through a smaller model and bump the low-confidence picks to Gemma. The filing pick (which
of these 12 motifs, none to three) on 240 confirmed claims, the same shortlist for each, four requests at once:

| Picker | Their motifs found | Picks not theirs | s a claim |
|---|---|---|---|
| Gemma 4 26B (today's) | 64% | **24%** | 3.5 |
| Gemma 4 12B | **67%** | 32% | 2.4 |
| Ministral 3 14B | 65% | 35% | 6.3 |
| Qwen3.5 9B | 58% | 32% | 1.2 |
| Gemma 12B, bumped under a fit of 0.85 (20%) | 69% | 30% | 3.1 |
| Qwen3.5 9B, bumped under a fit of 0.85 (22%) | 63% | 28% | 2.0 |
| the two small ones, bumped when they disagree (57%) | 64% | 24% | 5.6 |

The confidence model's fit (held out by claim, its reranker and filing-model signals left out) doesn't single out the
small models' wrong picks: they land on motifs that look right. Agreement of two small models does, but bumps more
than half, so it costs more than asking Gemma 26B. Four at once Gemma 26B is fast enough (3.5 s a claim) and makes a
third fewer wrong picks, the person's time to fix. It keeps picking; its yes-or-no can go to Nimble 9B (J1).
`scripts/experiments/c1_cascade.py`.

### E8 The picking prompt with nearest claims only (Oct 9) — no difference

Today's picking prompt, each motif shown with its three claims nearest the claim instead of its latest three, on the
same 145 confirmed claims and shortlists as E0.4: latest, 161 of the 239 motifs of theirs in the shortlist found (67%),
25% of picks not theirs; nearest, 158 (66%), 24%. Within the noise; the prompt stays. `scripts/experiments/e8_picking_nearest.py`.

### The learned shortlist in production (Oct 8)
motif_retriever.train_learned: the harness's weighting over every live signal ('today', the FACTS, motif_signals.CHEAP
with the news out and the layers), trained on the person's 428 confirmed claims, each held out of its motifs. Its own
five-fold test, by claim: plain weights 79.8% of the person's motifs in the top 12, learned **83.9%**. Filing uses it
from the next run (motif_index.file_claims), retrained daily, kept only while it tests better.

## In progress and planned (Oct 8)

Ideas for the hard misses (the person reads the structure under a claim; every finder reads its topic):

- **E1 Subtract the news.** The main directions the day's headlines vary along are topic; project them out of claims
  and notes before comparing, leaving something closer to framing.
- **E2 Imagined instances.** Gemma writes ten claims per motif from its note, each about a different topic, so a
  one-claim motif matches across topics.
- **E3 Motifs travel in bundles.** Which motifs the person files together (a claim in *Pious hypocrite* is often in
  *Double standard*): suggest a claim's further motifs from its likeliest first ones. Used only to suggest filings,
  never as a link between motifs (co-occurrence isn't relatedness).
- **E4 A jury of readers.** Gemma's yes or no as several readers (a folklorist, a rhetorician, a partisan of each side),
  averaged; their disagreement as a signal.
- **E5 Spread over the person's links.** A motif's score borrows from its rests-on, related and group neighbours (a
  graph convolution).
- **E6 Ask what teaches most.** Simulate choosing which filings to ask the person about by the model's uncertainty, not
  at random: does it reach the same accuracy with fewer checks?
- **E7 The layered finder.** Gemma describes a claim layer by layer (character, plot, argument, value); each layer
  matched to motifs of that genre (the layered prompt found +64% of hand-adds on Oct 7, with many extra picks).
- **E8 The picking prompt with nearest claims only** (E0.4's other half).
- **E9 Fine-tune the reranker** on the person's decisions (overnight: it needs the GPU to itself).
- **C1 A cascade** (the person, Oct 8: run everything through a smaller model, and bump the low-confidence picks to a
  Gemma round). The filing pick asked of Qwen3.5 9B and Gemma 4 12B (both fit the card whole) and Gemma 4 26B (today's,
  partly on the CPU) on 240 of the person's confirmed claims, the same shortlist for each; then, with no model asked,
  each small model's picks bumped to Gemma 26B when the confidence model's fit is under a line (trained on the other
  claims' decisions only, its reranker and filing-model signals left out), when it picks nothing, or when the two
  small models disagree. Found, wrong picks, share bumped and seconds a claim for each.
  `scripts/experiments/c1_cascade.py`.
