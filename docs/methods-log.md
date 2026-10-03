# Methods log

Every change to how bignews.day collects or measures things, dated. A chart that crosses one of these dates should be
read with the change in mind. Newest first. Scores in the database carry `scored_by` (model plus a rubric hash) from
2026-10-03 on; earlier scores say `qwen3:8b rubric:pre-tracking`.

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
