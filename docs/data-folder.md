# The data folder

Everything the app keeps lives in one folder: `~/maudlin-data`, which `data/` in each checkout links to. Set
`MAUDLIN_DATA` to point a process somewhere else; the experiment queue does this to give experiments a copy of their
own. This page says what each file is, which module owns it, and whether losing it matters. It was written on Oct 21
after Fable's architecture review found 75 JSON files and six databases with no list of them. Add a line here when you
add a file.

Kinds of file:

- **Work** is the person's own curation. It can't be made again, so it is backed up every hour.
- **Store** is what the pipeline gathered or decided. Most of it can be gathered again, but slowly or not at all,
  since feeds move on.
- **Cache** can be deleted. It costs time, model calls or GPU minutes to rebuild.
- **Log** is history kept for measurement and debugging.
- **State** is a small file that coordinates processes.

## The person's work

| File | Owner | What it holds |
|---|---|---|
| `motif_index.json` | `analysis/motif_index.py` | Motifs, filings, links, groups, genres, corrections, tellings and held claims. Every write is locked (`.lock`). |
| `curation.sqlite` | `analysis/curation_db.py` | Every version of the motif index, the saved states, and a copy of the curation log. |
| `motif_proposals.json` | `analysis/motif_proposals.py` | The machine's proposals, with the person's decisions and critiques. Decided ones are kept for good. |
| `validation/curation_log.jsonl` | `scripts/validate.py` | Every change made in the checker, with what it replaced. The models learn from it. |
| `validation/motif_verdicts.jsonl` | `scripts/validate.py` | Answers given on the claims-to-judge page. |
| `validation/undo/` | `scripts/validate.py` | The checker's undo stack: the last 50 changes. |
| `validation/today.json` | `scripts/validate.py` | The day's set of decisions. |
| `motifs/casebook.md`, `motifs/LICENSE` | the person | The casebook, and the index's license. |
| `headline_labels.csv` | `analysis/newsfilter.py` | Headlines labelled news or not, which train the news filter. |
| `entity_aliases.json`, `always_named.json`, `never_named.json` | `analysis/entities.py`, `analysis/accusations.py` | Name lists kept by hand. |

## Stores

| File | Owner | What it holds |
|---|---|---|
| `data.db` | `models.py` (Alembic) | Headlines, articles, outlets, stories, sagas, side feeds and transcripts. |
| `vernacular.sqlite` | `vernacular.py` | Bluesky and Mastodon posts, with authors salted (`vernacular_salt`). |
| `show_claims.json`, `show_claims_retold.json` | `analysis/show_claims.py` | Claims read from show transcripts, and the ones retold on two or more shows. |
| `focus_group_claims.json` | `analysis/focus_group.py` | Claims voters made in The Focus Group. |
| `factcheck_labels.json`, `factcheck_texts.json` | `analysis/factchecks.py`, `analysis/factcheck_text.py` | Fact-checks read as claims, and the text of each piece. |
| `factcheck_*links.json`, `factcheck_seen.json` | `analysis/factchecks.py`, `analysis/circulation.py` | Fact-checks tied to stories and narratives. |
| `narratives/report-*.json` / `.md` | `narratives.py` | Each night's report on groups of posts. `nightly()` files the latest one. |
| `narratives/stance_judgments.json`, `narratives/judgments.json` | `analysis/circulation.py`, `narratives.py` | The model's answers about narratives. |
| `motifs/watch_list.json` | `analysis/watch_list.py` | Plain-news claims waiting to be filed again. |
| `motifs/filing_alternatives.json` | `analysis/filing_confidence.py` | Other motifs where weakly filed claims might belong. |
| `motifs/motif_elements.json` | `analysis/motif_signals.py` | The judge's "must-have" element for each motif, drafted by the model. |
| `story_*.json`, `saga_*.json`, `sagas_ended.json` | `analysis/stories.py`, `analysis/sagas.py` | Story labels, merges, splits, returns and seams, and the saga judge's answers. |
| `scotus_*.json` | `analysis/scotus.py` | The docket, and the model's glosses and judgments. |
| `episode_kinds.json`, `running_order.json`, `feed_transcripts.json`, `sidefeeds_state.json` | `episode_kind.py`, `analysis/running_order.py`, `sidefeeds.py` | Show episodes labelled news or evergreen, radio running orders, and feed transcripts with their state. |
| `chyrons/` | `chyrons.py` | TV chyron OCR, cleaned and matched to stories. |
| `polls.json`, `aggregates.json` | `polling.py` | Polls. |
| `accusations.json`, `edit_judgments.json`, `satire_links.json`, `subject_tags.json`, `story_entities.json`, `story_extras.json`, `investigations.json`, `outlet_wiki.json`, `bluesky_examples.json`, `newsiness.json`, `newsday.json`, `cloud_history.json` | each named module | Site features. Each can be rebuilt over days. |
| `archive/` | `site/archive.py`, `site/page_story.py` | Each day's front page, and story pages, kept. |
| `archives/` | `scripts/experiments/archive_db.py` | Outside corpora and the archive experiments' database. Large. In the nightly backup only. |
| `motifs/experiments/` | `scripts/experiments/` | Experiment data, the catalog (`experiments.sqlite`), and logs. In the nightly backup only. |

## Models the pipeline trains

| File | Owner | Rebuilt |
|---|---|---|
| `filing_confidence.json` | `analysis/filing_confidence.py` | Daily, from the curation log. |
| `motif_retriever.json`, `motif_shortlist_learned.json` | `analysis/motif_retriever.py` | Daily. |
| `motifs/reranker/` | `analysis/reranker_teach.py` | Weekly. It is the taught Qwen3 reranker: 181 MB. |
| `newsfilter.joblib` | `analysis/newsfilter.py` | Only by hand (`main.py --train-newsfilter`). |
| `motifs/news_directions.npz` | `analysis/motif_signals.py` | Daily, from the latest headlines. |

## Caches

All of these can be deleted. Each costs time to rebuild.

| File | Owner | What it holds |
|---|---|---|
| `story_embeddings.sqlite` | `analysis/embeddings.py` | mxbai vectors of headlines. Unused ones are kept seven days. |
| `narratives/embeddings.sqlite` | `analysis/embeddings.py` | mxbai vectors of posts, claims and motifs, kept four days. The filing signals' nomic, Qwen3-Embedding and Arctic vectors are kept thirty. It is the biggest cache, at 3.7 GB. Run `python -m app.analysis.embeddings vacuum` on an idle hour to give back its free pages. |
| `motifs/claim_shapes.json`, `motifs/claim_layers.json` | `analysis/motif_signals.py` | The model's bare shape and layers for each claim. |
| `motifs/rerank_cache.json`, `motifs/pair_judge_cache.json` | `analysis/motif_signals.py` | Reranker and judge answers for each claim and motif pair. |
| `favicons/`, `llm_tokens/` | `site/favicons.py`, `analysis/token_log.py` | Outlet icons, and token counts per day. |

## Logs

| File | Owner | What it holds |
|---|---|---|
| `app.log` | `utils/logger.py` | Every process's log. Rotated at 25 MB, three old copies kept. |
| `motifs/trace/` | `analysis/trace.py` | Each stage a claim passes through, one file a day. It feeds the checker's live page. |
| `motifs/filing_log.jsonl` | `analysis/motif_index.py` | One line per filing run. |
| `motifs/shortlist_log.jsonl` | `analysis/motif_index.py` | Each new claim's shortlist. Prometheus scores it weekly. |
| `motifs/refile_log.jsonl` | `analysis/watch_list.py` | Plain news filed again. |
| `motifs/metrics.json`, `motifs/model_history.jsonl` | `analysis/motif_index.py`, `analysis/filing_confidence.py` | Index statistics over time, and each confidence model trained. |
| `scraper_history.json`, `scraper_check.md`, `health.json` | `scraper_health.py`, `health.py` | Outlet and feed health. |
| `gpu_log.csv`, `lights_log.csv`, `model_scout.json` | the gpu-log unit, `lights.py`, `scripts/model_scout.py` | The machine. |

## State

`worker.json` (the worker's heartbeat), `gpu_lease.json` (who holds the GPU), `lights_place.json`, and the `*.lock`
files.

## Attic

`attic/` holds data that no code reads any more, moved there instead of deleted. Its own README says what each part
is. The backups skip it.

## Leftovers

These are left by one-off jobs, and nothing in the pipeline reads them. Delete them once you're sure:

- `motifs/*.with-test-rows-2026-10-14.jsonl`: the copies `scripts/drop_test_rows.py` kept.
- `motifs/glean.json` and `glean_score.log`: from `scripts/glean_filings.py`. The Tell-Tale Hat experiment reads
  `glean.json`.
- `narratives/backup-before-keys-2026-10-06/`.
- `rescore.log`.
- `epithet_candidates.json`.
- `validation/verdicts.jsonl`: from the old headline mood page.
