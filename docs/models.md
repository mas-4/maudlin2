# Models: what runs where, how each was chosen, and what's waiting for a test

Every model bignews.day uses runs locally (Ollama on an RTX 3080 with 10 GB and 125 GB of RAM; faster-whisper on the
same GPU). Models are chosen by tests against a person's own judgments (motif filings, label verdicts, hand vetoes),
not by public benchmarks. A model is switched for a job only after that job's own test. Each switch is also in the
methods log (`docs/methods-log.md`).

To upgrade a job: run its test with the candidate models, compare against the person's judgments, switch the constant
named below, note it here and in the methods log.

## Installed

| Model | Size | Kind | Notes |
|---|---|---|---|
| qwen3:8b | 5.2 GB | dense, fits the GPU | the default for labelling (`llm.DEFAULT_MODELS`) |
| qwen3:14b | 9.3 GB | dense | untested |
| qwen3:30b-a3b | 18 GB | mixture of experts, 3B active | the bigger model for hard jobs since Oct 4 |
| qwen3.5:9b | 6.6 GB | dense | Oct 2026 release; bake-off Oct 5 |
| qwen3.5:35b | 22 GB | mixture of experts | bake-off Oct 5 |
| gemma4:12b | 8 GB | dense | bake-off Oct 5 |
| gemma4:26b | 18 GB | mixture of experts, 3.8B active | **motif filing, Focus Group, radio running order since Oct 6** |
| gpt-oss:120b | 65 GB | mixture of experts, ~5B active, mostly in RAM | best in the Oct 5 bake-off, ~29 s a call |
| mxbai-embed-large | 0.7 GB | embeddings | stories, narratives, motif search, wire share and curators (Oct 5) |
| potion-base-8M / 32M | small | static embeddings, CPU | sagas (stays, Oct 5 test), fallback when Ollama can't embed |
| faster-whisper large-v3-turbo | — | speech to text | podcast, radio and Focus Group transcripts |

A known quirk: **Qwen3.5 under Ollama returns an empty list when the JSON schema asks for a list of fixed strings**
(an `enum` of strings), even when its reasoning names the answer. Ask for numbers instead. Before moving any job to
Qwen3.5, change its schemas that way.

## Jobs

| Job | Code | Model | How it was chosen | Status |
|---|---|---|---|---|
| Motif filing: judge the 8 closest motifs side by side; name a new one only if none fits | `motif_index.JUDGE_MODEL` | **gemma4:26b** | Oct 5–6 tests on the person's settled filings (below) | switched Oct 6 |
| Motif matching of a new name to an existing motif | `motif_index.MODEL` (`match`) | qwen3:30b-a3b | Oct 6, against the person's 31 merges (the merged motif's name should match where it went) and 45 "not the same" verdicts. At the old floor (0.7) the right motif reached the model for only 7 merges; at 0.6, for 20: 30B found 14 and joined 2 of 26 not-same pairs (5 s); qwen3:8b 13 and 3 (1.2 s); gemma4:26b 12 and 1 (3.4 s); gemma4:12b 11 and 1. Too few cases to separate the models; the floor was the real gap | kept; floor lowered to 0.6 Oct 6 |
| Motif scope-note drafts | `motif_index.GLOSS_MODEL` (`gloss`) | **gemma4:26b** | Oct 6, drafts for the 49 motifs whose notes the person wrote, compared with theirs by meaning (mxbai): gemma4:26b 49 drafted, 0.73; qwen3:30b-a3b 39 (gave up on 10, judging or naming people), 0.71, and it restated single claims; gemma4:12b 49, 0.71; qwen3:8b 45, 0.69. Read side by side, Gemma tells the kind of story better but opened half its drafts with the motif's name ("Breaking ranks occurs when..."): such a draft is now asked again, which leaves 43 drafted, none opening with the name, 0.73 | switched Oct 6 |
| Saga judge ("one running story?") | `sagas.JUDGE_MODEL` | **gemma4:26b** | Oct 6, 46 story pairs labeled by Claude (11 the same story): Gemma 40 of 46 agree, found 5 of the 11, none wrongly joined, 2.2 s a pair; qwen3:30b-a3b 41/46, 7 of 11, 1 wrongly joined, 33 s; qwen3.5:35b 40/46, 6, 1 wrong, 2.8 s; gpt-oss:120b as Gemma at 26 s. A wrong join is what a person has had to veto, so none wrong won. Reworded the same day (angles, consequences and reactions are one story; a different focus is no reason for "separate"): 42/46, found 7 of 11, none wrong | switched Oct 6 |
| Saga names | `sagas.py` | qwen3:8b | — | untested |
| Narrative threads ("same narrative told again?") | `narrative_threads.MODEL` | **gemma4:26b** | Oct 6, the 32 pairs the live code had asked about, labeled by Claude (21 told again, 9 not, 2 too close to call), each model twice: Gemma 18 of 21 found in both runs, 1 of 9 wrongly joined, 1.8 s a pair; qwen3:30b-a3b 15 and 17, 1 (missed plain repeats: the same Nobel prize, Sánchez's snap election); gemma4:12b 21, but 2-3 wrong; qwen3:8b 11, 2. Threads rebuilt with it (17 told on 2+ days, was 16) | switched Oct 6 |
| Accusations screen: does a claim say a named person committed a crime, and are they well known? | `accusations.MODEL` | **gemma4:26b** | Oct 6, read by hand on the first claims: it found Jacob Geller (rape), Wanying Zhang (spying), and kept Musk, Diddy and officials named; it didn't know Howard Lutnick holds office, so anyone our headlines name in 3+ articles stays named too; it listed people with no crime ("none"), now ignored | in use since Oct 6 |
| A story back on the front pages: the same news event as one that left them? | `stories.RETURN_MODEL` | **gemma4:26b** | Oct 7, the 42 pairs the rule would have asked about in the week before (stories that left the front pages in the 48 hours before another began, sharing 2+ frequent words): joined only the Nobel pair, none wrongly (two Dodgers games, Cornell developments, Fairford arrests all 'different'); the first wording refused the Nobel pair over one stray headline | in use since Oct 7 |
| Correction proposer: typos, kind-of, related, merges, groups for the motif index | `motif_proposals.MODEL` | **gemma4:26b** | the same model as filing and the saga judge; judged by the person's approvals and rejections in the workbench | in use since Oct 7 |
| Motif shortlist for filing (which motifs the filing judge sees) | `motif_retriever.shortlist()`, weights `motif_retriever.json` | mxbai-embed-large likenesses (the motif's text, its name and note, its nearest claim, its claims' center, its size, its kind-tree neighbours), weighed by a logistic regression trained daily on the person's confirmed filings; top 8 plus their broader motifs and kinds (up to 6) | 766 confirmed filings, held out: the shortlist held 74% of the person's motifs (the closest 8: 60%) and 61% of those they had added by hand (40%). With Gemma's pick on all 372 claims: 375 of 763 of their motifs found (closest 8: 322), 47 of 206 hand-added (33), the same 16 picks they had removed | in use since Oct 7; falls back to the closest 8 without weights |
| Proposal judge and best fit: how likely the person approves a kind-of or related proposal | `motif_proposals.JUDGE_PROMPT`, `best_fit()` | **gemma4:26b** scores 0-10 (shown 8+8 of the person's decisions); a logistic regression over that score and plain facts, trained on the decisions | 144 decisions held out: the judge alone scored most approved and rejected alike (2-3); its first, "strict" prompt rejected 32 of 37 approved. Best fit's fold took 29 of 65 rejected, 8 of 79 approved | in use since Oct 7: sorts the checklist, folds the unlikely; nothing hidden |
| Narrative to news story link (folklore cards, story and saga pages) | `narratives.STORY_MODEL` | **gemma4:26b** | Oct 7, the 346 links the small model (qwen3:8b) had made, asked again: they differed on 42; read by Claude, Gemma right on ~25, the small model on ~11 (3 too close); wrong joins 5 to 7 (the small model put an accusation against a YouTuber on the Cornell case); missed links 3 to ~20 | switched Oct 7 |
| Focus Group voter claims | `focus_group.MODEL` | **gemma4:26b** | Oct 6, 12 transcript parts: all quotes found for every model; Gemma's claims the voters' own with sides; the 30B took a host's analysis for a voter's; Qwen3.5 35B found more but no sides | switched Oct 6 |
| Focus Group check: is the quote evidence for the claim? | `focus_group.SUPPORT_MODEL` | **gemma4:26b** | Oct 6, prompt tuned on 16 stored claims and the known bad ones (14 of 16 passed, bad ones caught) | in use since Oct 6 |
| Radio running order | `running_order.MODEL` | **gemma4:26b** | Oct 6, 10 newscasts: 96% of its stories passed the first-words check (30B 81%), front-page picks nearly the same (28 of 30), 6 s a newscast | switched Oct 6 |
| TV chyron matching to front-page stories (per channel-hour) | `chyrons.MATCH_MODEL` | **gemma4:26b** | Oct 6, an hour of Fox and CNN read by hand: matches right, the channels' own topics left unmatched; embeddings at 0.75 had missed terse captions and let wrong ones through | in use since Oct 6 (embeddings as fallback) |
| TV chyron OCR cleanup (kind of line, corrected text) | `chyrons.CLEAN_MODEL` | **gemma4:12b** | a 30-line test batch, Oct 6: invented nothing (26B changed Iowa to Ohio; 8B kept garble) | in use since Oct 6 |
| Headline labels (mood, spice, feelings) | `newsfilter.py` | qwen3:8b | — | waiting: 19 label verdicts so far, needs more |
| Story labels, names in stories, fact-check labels, narrative labels, SCOTUS judging and glosses, edits, subjects, ties, circulation | various | qwen3:8b | — | untested |

## Motif filing tests (Oct 5–6)

The answer key: 160 claims a person had settled on the motif board (in a motif when it was marked done, or in a motif
they named), each held out of the index and filed again.

- The old live method (the 15 closest motifs, one call to pick or name, qwen3:30b-a3b): the person's motif for **37%**
  of claims; 52% of its picks were theirs.
- Shapes (three de-named retellings per claim to find candidates, a yes/no check per candidate): 47%, but only 28% of
  picks theirs. Finding candidates by shape was worse than by the claim's own words (the person's motif among the 6
  closest: 58% against 74%). Dropped.
- Side by side (the 8 closest motifs by the claim's words, one call: which of these, none to three?), 60 of the claims:
  gpt-oss:120b 62% (56% of picks theirs, 29 s a claim), qwen3.5:9b 60% (48%, 1 s), qwen3.5:35b 58% (50%, 3 s),
  gemma4:12b 58% (46%), gemma4:26b 57% (54%, 2.4 s), qwen3:8b 53% (42%), qwen3:30b-a3b 52% (52%). The person's motif
  was among the 8 for 46 of the 60 claims, so 77% at most.
- Offering "or name a new motif" in the same call lowered gemma4:26b to 50%; asking it separately, only when nothing
  fits, gave 65% (66% of picks theirs) on the same candidates. Live code on the index of Oct 6: 53% (57% with the scope
  notes, which were written after seeing these claims).
- Runs of the same model and prompt differ by several points; 60 claims can't separate models a few points apart.
  Every side-by-side model beat the old method.

## Next

1. Every 30B job now has its test (Oct 6): only motif matching stays on qwen3:30b-a3b.
2. The 8B labeller against qwen3.5:9b and gemma4:12b, once there are enough label verdicts.
3. gpt-oss:120b for small, hard jobs where 30 seconds a call is affordable.

## Considered and not taken

- **Pydantic AI / Pydantic AI Harness** (suggested Oct 6). The Harness is for long-running autonomous agents (shells,
  file workspaces, subagents, memory), and bignews.day has no agents: every model job is a single structured call,
  made through `app/analysis/llm.py`, with Ollama limiting the answer to the job's JSON schema. Plain Pydantic AI
  could swap those dict schemas for Pydantic classes with validation and retries. But the failures we've had were
  failures of judgment, not of shape: a claim its quote didn't support, Iowa changed to Ohio, a story missed. Schemas
  can't catch those; tests against a person's judgments do. Worth another look if the schemas get hard to maintain.
