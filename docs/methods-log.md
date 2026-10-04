# Methods log

Every change to how bignews.day collects or measures things, dated. A chart that crosses one of these dates should be
read with the change in mind. Newest first. Scores in the database carry `scored_by` (model plus a rubric hash) from
2026-10-03 on; earlier scores say `qwen3:8b rubric:pre-tracking`.

## 2026-10-04
- **Podcast transcription.** Archived podcast audio is transcribed on our own GPU with Whisper (faster-whisper
  large-v3-turbo, int8), after each hourly build, hourly newscasts first, for items up to 3 days old. Sponsor reads
  at the start and end are trimmed. Transcripts are kept with the model's name, for analysis only.

## 2026-10-03 (evening)
- **Shows archive begins.** 40 newsletters, podcasts and political video channels are collected into side_item
  (append-only), each feed read at most every 2 hours with conditional requests. Sources are sorted by how they
  follow the news (news of the day vs. thinking, #135), not format; only news-of-the-day ones are shown on the site.
- **Stories: different money stays apart.** Headlines that both name dollar amounts more than 3x apart can't link
  ($90 Medicare checks vs. a $5,000 promise); $90 vs. "nearly $100" still can. Headlines without amounts unchanged.
- **Stories: a split story gets two titles.** When one saved story's coverage splits into two clusters in an hour,
  the bigger part keeps the story and its title and the smaller becomes a new story (before, both showed the same
  title).
- **Headline changes: live-blog filter.** Only an all-caps LIVE tag or phrases like "live updates" mark a live
  blog; the plain word "live" no longer does, so ordinary rewrites containing it now count.
- **Scraping.** Bare photo credits with no text left after cleaning are dropped; hrefs with stray spaces are kept.

## 2026-10-03
- **Score provenance.** Each scored headline now records which model and rubric version scored it, when, and the
  model's own note on who the event affects. The rubric id is a hash of the prompt and schema, so it changes on any
  edit to either.
- **Trend sightings.** Every appearance of a trend in a source's list is now logged with its rank (before this, only
  first and latest sightings were kept).
- **Outlet ratings.** Lean switched from MBFC to AllSides (5 levels, CC BY-NC 4.0); reliability from Wikipedia's
  perennial sources list (CC BY-SA 4.0). Outlets AllSides doesn't rate are left out of every lean average.
- **Our lean estimate.** Wording-only model (tf-idf + ridge) trained on rated outlets over 30 days; published only
  when leave-one-out rank agreement is 0.45+ and the outlet is 0.55+ from center. Never counted in lean averages.
- **Emotions.** Ranked top three per headline, averaged ranked-choice style (3:2:1). All headlines rescored with this
  rubric (14,404).
- **Stories and sagas.** Stories: headlines linked at embedding similarity 0.7+, six or more outlets, 24-hour lookback.
  Sagas: stories whose centers are 0.58+ similar and share a distinctive word.
- **News-day sticker.** Live headlines only; a story's weight is full for 12 hours, then halves every 24 hours.
- **Duplicates merged.** 2,470 duplicate articles and 1,468 duplicate headlines merged (backup kept).
- **New outlets.** 11 added from their feeds (TPM, Puck, The Washington Sun, The Lever, Mediaite, Straight Arrow
  News, UnHerd, Just the News, The Daily Signal, The American Conservative, Washington Reporter). Vox and National
  Review switched to their feeds.

## 2026-10-02
- **Archive begins.** The current database starts this day; anything earlier isn't in it.

## History
- **2024-01 to 2024-08: built by hand** as Maudlin: per-outlet scrapers, the database, the word cloud, word-list
  sentiment (VADER, AFINN). About 680 commits.
- **2026-10: rebuilt with AI assistance** (Anthropic's Claude as a coding assistant) for the 2026 midterms. The
  direction, design and decisions are the maintainer's; the assistant wrote and tested much of the new code.
  Separately, the site's measures come from a small open model run locally (see above for its provenance).
