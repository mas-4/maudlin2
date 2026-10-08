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
40 directions), a signal of the filing confidence model from its next retrain.

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
