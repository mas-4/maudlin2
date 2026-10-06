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
| Motif matching of a new name to an existing motif | `motif_index.MODEL` (`match`) | qwen3:30b-a3b | — | untested |
| Motif scope-note drafts | `motif_index.MODEL` (`gloss`) | qwen3:30b-a3b | prompt tuned by eye Oct 5 | untested against others |
| Saga judge ("one running story?") | `sagas.JUDGE_MODEL` | qwen3:30b-a3b | the 8B refused real parts (Oct 5) | untested against new models; test set: saga_judgments.json hand vetoes |
| Saga names | `sagas.py` | qwen3:8b | — | untested |
| Narrative threads ("same narrative told again?") | `narrative_threads.MODEL` | qwen3:30b-a3b | — | untested |
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

1. The other 30B jobs, one at a time, each with its own test (saga judge against the hand vetoes; Focus Group by quotes
   found; running order by first words found; narrative threads by a person's checks).
2. The 8B labeller against qwen3.5:9b and gemma4:12b, once there are enough label verdicts.
3. gpt-oss:120b for small, hard jobs where 30 seconds a call is affordable.

## Considered and not taken

- **Pydantic AI / Pydantic AI Harness** (suggested Oct 6). The Harness is for long-running autonomous agents (shells,
  file workspaces, subagents, memory), and bignews.day has no agents: every model job is a single structured call,
  made through `app/analysis/llm.py`, with Ollama limiting the answer to the job's JSON schema. Plain Pydantic AI
  could swap those dict schemas for Pydantic classes with validation and retries. But the failures we've had were
  failures of judgment, not of shape: a claim its quote didn't support, Iowa changed to Ohio, a story missed. Schemas
  can't catch those; tests against a person's judgments do. Worth another look if the schemas get hard to maintain.
