# Methods log

Every change to how bignews.day collects or measures things, dated. A chart that crosses one of these dates should be
read with the change in mind. Newest first. Scores in the database carry `scored_by` (model plus a rubric hash) from
2026-10-03 on; earlier scores say `qwen3:8b rubric:pre-tracking`.

## 2026-10-04
- **How a claim's motif is judged.** A motif is the story's shape as its tellers tell it: not whether it's true, and
  not whether a poster tells it or argues against it. (Calling a claim a "false accusation" puts a verdict into
  the classification; that's the fact-checkers' part, shown separately.) The site presents shapes only in the
  tellers' voice ("the story casts…"). The model's prompt and the hand check ask the same question.
- **A folklore card withheld after a misreading.** "Trans women are predators and their identities are inherently
  tied to dark kinks", told by 12 people and labeled right-wing, was a group of mostly trans people talking about
  their own gender; one post's line, from one trans woman arguing with others, became the group's "shared claim".
  It's withheld by hand (data/narratives/withheld.json). Cause: the finder groups posts by topic and the labeler
  writes a claim even when most posts don't concern it. Fix (next report): a narrative counts only if most of its
  sampled posts are about its claim, telling it or arguing over it alike.
- **Fact-checks (#153).** Seven fact-checkers' feeds are archived (PolitiFact, FactCheck.org, Snopes, Lead Stories,
  Full Fact, NewsGuard Reality Check, Science Feedback; Check Your Fact was dropped: its feed is mostly the Daily
  Caller's ordinary news). Each check from the last week is tied to a current story, and each from the last 30
  days to a folklore narrative, the same way as satire: the closest three at 0.6+ similarity, then the model picks
  one or "none". Shown with its title (which usually carries the verdict) on story and folklore cards.
  - Checked by hand on Oct 4. Below 0.58 the closest pairs were mostly another claim on the same subject
    (FactCheck.org on Trump's taxpayer-funded ads matched Ken Paxton's ads at 0.56). The first prompt ("the same
    event or the very claim") made the model answer "none" even when its own reason said the check was about the
    story; asking for "N claim" / "N event" / "none" made it worse (no story ties at all). Asking only for the
    number, and saying a check of a fake video or rumor about an event is about that event: 7 ties, 6 right
    (FlyDubai, Cornell ×4, Christa Pike), 1 on the same subject rather than the same event (an AI-safety check
    tied to the "Super Intelligence Force" narrative). The satire ties (now the same code) were unchanged, 3 of 3.
- **Call-in shows archived and transcribed (research only, #153).** Seven shows whose free feeds carry full hours
  with callers: Jesse Kelly, Clay Travis & Buck Sexton, Michael Berry, Mark Levin (right); Brian Lehrer (WNYC),
  KQED Forum, 1A (public radio). No free feed on the left carries callers (Thom Hartmann's and the Majority
  Report's caller hours are YouTube-only or for paying members), so public radio stands in there; the sample
  leans right. C-SPAN's Washington Journal, which sorts callers by party line, has no feed and its archive runs
  on a lag, so it's out. Never shown; callers are private people, so only patterns will be published.
- **Satire (#139): which stories become jokes.** Ten satire sites are read every two hours (the Babylon Bee; the
  Onion, Borowitz, New Yorker humor, McSweeney's, Reductress, the Hard Times, NewsThump; Duffel Blog, ClickHole;
  leans by reputation). Each joke from the last three days is offered the closest current stories with
  mxbai-embed-large similarity 0.5 or more (up to three) and the model picks one or "none". Shown only as 🃏
  "joked about by" on the story card, never as coverage or in any measure.
  - Checked by hand on Oct 4. With no similarity floor, the model tied 6 jokes to stories and 2 were wrong, both
    on a shared word ("Woman survives two minutes in Primark" -> a botched execution; a paste-eating Marine -> a
    Marine arrested in Japan). Asking it to name the event the joke mocks first made it worse (9 ties, 4 wrong).
    Every wrong tie was under 0.48 similarity and three of four right ones over 0.54, so with the 0.5 floor: 3
    ties, all right. Missed: the Bee's oblique Cornell joke (0.44). With only the fallback embeddings, satire is
    skipped rather than matched on another scale.
- **Mood redefined: how the headline presents the news (rubric b31d654f).** Mood was how good or bad the event is
  for the people it affects, whoever reports it. For political news that depends on whose side you're on, so the
  model picked a side itself and a reader couldn't check it: RedState's "Oh, Hell No: Judge Rules Federal
  Noncitizen Voting Ban Unconstitutional" scored ☀️ upbeat+ (good for noncitizens). Mood is now whether the
  headline presents its news as good or bad, from the outlet's own words and tone; plainly reported harm is still
  grim. Spin now also counts outrage bait in plain words ("Oh, come on:").
  - Tested on 21 headlines (12 hand-checked in the label check, nine outlets' headlines on that ruling): mood exact
    13 vs 10 under the old rubric, within one step 19 vs 16. On the hand-checked 12 alone, exact 6 vs 6 and
    within one 10 vs 9; the one sign flip (the Daily Wire's "Leftism's appetite for the destruction of order"
    read as upbeat+) is fixed. The ruling set's expected moods are the assistant's reading, not a hand check.
  - Every stored headline is rescored with the new rubric (`--rescore-outdated`, between hourly runs). The old
    scores are kept in `data/archive/scores-before-rescore.csv` with the rubric that made them. Mood before and
    after Oct 4 means different things, so any mood trend starts here.
- **Shortened links scrubbed (privacy fix).** Bluesky writes links in a post's text shortened and without
  https:// ("youtu.be/…", "twitch.tv/someone"), so the scrubber missed them: 4,998 stored posts kept a full link,
  some naming an account. They now become their site like every other link, and the stored posts were rewritten.
  Posts need six real words to be grouped: a run of emoji and a video link is promotion, and a ring of such posts
  had reached the page as an 11-person "conspiracy theory".
- **Folklore page floor: 10 people.** In the first full report (25,095 accounts), half of the 60 retold narratives
  had five to nine tellers, and those were mostly a handful reacting to one news item or game. The page shows
  narratives told by at least 10 people, or 1 in 2,500 accounts sampled if that's more; the report keeps the rest.
- **Shared article links kept (research only).** A link in a post to an article on a site we scrape is kept whole
  (without its query string), since it ties the post to a story exactly; other links are still cut to their site.
- **What people say, unprompted (research only, #153, #142).** Each run samples five minutes of Bluesky's public
  stream (Jetstream) and three pages of mas.to's federated timeline, on a thread during the scrape. Kept: post text,
  reply/quote flags, a salted fingerprint of the author. Handles in text become "@someone", links just their site;
  images and video are never fetched. Skipped: non-English (by script and common words, since posts often don't say),
  posts their authors labeled sensitive, sex spam, Mastodon accounts that haven't opted in to being searchable or are
  marked as bots. Deleted posts are deleted here too; raw text expires after 30 days. Once a night the day's posts are
  grouped into paraphrase groups (mxbai embeddings, mutual nearest neighbours at 0.78, accounts posting more than 20
  times in six hours and bare link shares left out), and each group of 5+ people is scored for wording variety (one
  minus mean word overlap): varied wording from many people is a told narrative, the same words copypasta. The local
  model labels the biggest groups: the shared claim, whether it's retold or just a shared topic, genre (rumor,
  contemporary legend, conspiracy theory, folk belief, joke formula, testimony, news reaction...), Thompson
  Motif-Index chapter and a motif, Propp-style roles (villain, victim, hero), politics and side. Each narrative is
  matched to current stories: the model chooses among the three closest stories ("same event", "same issue" or,
  most often, "none"). A yes-or-no check, one candidate at a time, agreed to nearly anything (a Drake Maye fumble
  "matched" voters calling J.D. Vance "a goober"); the forced choice linked 12 of 60 narratives on Oct 4, 10 of them
  rightly. Matching narratives to The Focus Group transcripts (12 episodes, Ep50-61, transcribed Oct 4) was tried and
  dropped from the page: the passages rarely overlap a day of social posts, and the yes-or-no matches were wrong
  almost every time. The first report (40 minutes of stream, 15,430 posts) found 13 retold narratives,
  among them a folk belief that Trump is being kept alive by doctors because "they need him alive" and a contemporary
  legend of "Julie bots". Reports stay in data/narratives; nothing is published.
- **Stories use a bigger embedding model.** Four models were compared on the day's 6,733 headlines at equal
  coverage (the threshold at which each put about 700, 900 and 1,100 headlines into stories of 6+ outlets), with
  precision from cross-outlet pairs sampled inside each model's stories and recall from a shared pool of 657 pairs
  sampled across every model's similarity range, all judged by the local language model under two wordings
  (agreement only; about 80 judged pairs per cell, so ±0.04). At ~900 headlines: potion-base-8M (until now)
  precision 0.77, recall 0.57; mxbai-embed-large 0.91, 0.57. At ~1,100: 0.82 / 0.64 against 0.88 / 0.68.
  potion-base-32M and nomic-embed-text fell between. Stories now use mxbai-embed-large through the local Ollama at
  0.80 (about 1,000 headlines in stories); its vectors are cached by headline, so each run embeds only new
  headlines. If Ollama can't embed, stories fall back to potion-base-8M at 0.70. Sagas, wire share and aggregator
  matching keep potion-base-8M, whose thresholds were tuned on its scale.
- **Each side's wording.** Story cards show two-word phrases that outlets on one side of the lean scale put in their
  headlines and no outlet on the other side did ("hero pilot" and "FlyDubai hijacker" from the right against
  "extremism concerns" and "terrorist act" from the left on the FlyDubai attack; "Trump doxes" against "Trump urges"
  on the senator's phone number). Our outlets lean left as a group, so a story needs 3 or more rated outlets on each
  side, and a phrase needs 2 or more outlets and a quarter of its side's outlets, with none on the other side.
  Function words and headline filler don't count; phrases the same outlets used back to back are joined ("small
  Texas town stopped Trump's"). No model involved.
- **Every-headline file packed.** headlines-table.json now lists each row's values in a fixed column order, with
  outlets (and their lean), topics, stories and feelings listed once and referred to by position, and URLs without
  "https://": about 12% smaller compressed (keys were a third of the raw file, but compression already removed most
  of that; URLs and titles are the bulk). The page unpacks it, and the download button saves the rows with named
  fields as before.
- **Cloud paper by spiciness.** Each word's scrap of paper is colored by how loaded the wording of its headlines is,
  white (plain) through cream to peach (spicy), instead of a random tint.
- **Supreme Court page (#144).** The term's cases come from the Court's Granted & Noted list (a public-domain
  government record); what each is about comes from its question presented on Wikipedia's list of pending cases
  (CC BY-SA), which the local language model puts in a few plain words ("Cook County AR-15 gun rights case"). Both
  are fetched at most weekly. Headlines naming the Court or a justice are read by the model with the outlet and its
  country (India's Supreme Court had been slipping in): whether each is about the US Supreme Court, which of the
  glossed cases it's about, a few topic words, and the stage it reports. A small model reading a list of thirty
  cases matched every term preview to five or six of them, and two headlines about Justice Alito and the Dobbs leak
  to the Arizona voter case, so a suggested case is kept only if the headline shares a word specific to that case
  (from its gloss, parties, question presented or the state court it came from, counting only words in at most two
  cases' texts) and the model, asked about that case alone, agrees it clearly refers to it. A distinctive party name
  ("Suncor", never "Congress") ties a headline to its case as well. Each case in the news gets a card like the front
  page's story cards: the lean of the outlets covering it against all Court coverage, mood, loaded wording,
  feelings, quoted phrases, and each side's most loaded headline side by side. Court news about no case on the
  docket is grouped by topic; docket cases no headline covered are listed. Window: 14 days; each outlet counts once
  per card.
- **Story coherence check tried, not adopted.** The model was shown each story's three most central headlines and
  asked about each loosely tied member (best similarity to that core under 0.75); rejected ones were taken out and
  clustered again among themselves. On Oct 4's headlines (labels as in the threshold test above, 90 pairs per setup):
  at 0.70 it raised precision from 0.87 to 0.91 but cut recall from 0.79 to 0.73; at 0.67 and 0.65 it didn't help,
  and the biggest stories kept their size (they were real stories: the FlyDubai attack ran to 121 headlines). All
  within the noise of the sample, so stories stay as they were.
- **Story threshold re-tested; it stays at 0.70.** Stories are still the connected groups of headlines whose
  embeddings are 0.70 alike or more. On one day's headlines (6,888) the local model judged about 1,000 headline
  pairs, under two wordings, keeping the pairs both wordings agreed on. One set was spread across the similarity
  range; it measures how many same-story pairs end up in one story (recall). The other was drawn from inside the
  stories each threshold would make, grouped by the highest threshold that still joins each pair; it measures how
  often a story's headlines really belong together (precision). Pairs that only join below 0.70 are the same story
  73% of the time between 0.675 and 0.70, 51% between 0.65 and 0.675, and 16% between 0.625 and 0.65, because
  low thresholds chain unrelated stories (the largest group grows from 127 headlines at 0.70 to 451 at 0.60). Scored
  with precision counting double (F0.5), 0.69 and 0.70 were best and within noise of each other. Lowering to 0.65
  catches more same-story pairs (recall 0.79 to 0.88) but drops precision from 0.85 to 0.75. Splitting the chains
  instead with Louvain communities or mutual nearest neighbors scored lower. A threshold has no gradient (scores move
  in steps as it crosses pairs), so it was swept every 0.005 from 0.55 to 0.80.
- **Saga links checked by the language model.** Before two stories first join a saga, the model reads a few headlines
  from each side by side and says whether they're one running story; the similarity and shared-name rules still
  apply first. A shared name alone had linked separate Supreme Court cases and separate plots by Iranian nationals.
  Verdicts are cached (saga_judgments.json); those two sagas were taken apart.
- **Headline A/B tests (#119).** Every wording Slate tests on a front-page card is recorded each run with when it was
  first and last up; when one is left, it's the winner. Shown on the headline changes page. Recording begins Oct 4.
  Checked on Oct 4 whether other outlets expose their variants the same way (each homepage once): none do. Outlets
  using Chartbeat's or Optimizely's headline testing run it in the reader's browser, so the variants never appear in
  the page a scraper reads.
- **Headline download.** The every-headline page links its rows as JSON (the file the table already loads).
- **Quote selection (#149).** Story cards list the phrases outlets put in quotation marks in their headlines (one
  headline per outlet, up to 4 phrases, most-quoted first), each tinted by the lean of the outlets that quoted it.
  Phrases of 2 to 80 characters count (an apostrophe inside a word doesn't open a quote); matching ignores case and
  punctuation, and each outlet counts once per phrase.
- **Daily editions begin (#125).** At each run the front page is saved as that news day's edition; past days are
  published as fixed pages under /YYYY/MM/DD/ with an archive index. Editions start Oct 4; earlier days have none.
- **Outlet pages (#126).** Each outlet gets its own page: live headlines and the stories they're in, recent
  rewrites, and the mix of feelings its headlines stir, over the outlets page's 30-day window.
- **RSS feed (#123).** feed.xml lists the current stories; each item keeps its id across runs while the story
  lives.
- **Aggregators aren't outlets (#151).** Google News, Drudge Report, RealClearPolitics and Political Wire no longer count
  toward stories, lean, the news-day sticker or the cloud (they mostly link to other outlets' stories); their live
  headlines are matched to stories (embedding 0.7) and shown as "picked up by" on the cards.
- **Wire share (#152).** Outlet cards show the share of an outlet's news headlines over 7 days that are AP or Reuters
  headlines near word for word (embedding 0.90 and 70% of words shared; checked by hand). Outlets mostly rewrite wire
  copy: on Oct 4 the highest was about 11%.
- **Story snapshots and trend arrows (#133).** Every run saves each story's lean, mood and outlet count
  (story_snapshot). Cards show arrows when lean or mood moved over the last 6 hours (needs 2+ hours of history):
  lean 0.15 / 0.35 / 0.6, mood 0.1 / 0.25 / 0.45 for one, two or three arrows.
- **Bright side removed.** Its picks (hope/joy plus a "widely good news" model check) read as feel-good filler rather
  than a measure.
- **Blindspots move onto story cards.** Same rule; the separate box is gone. A blindspot's card shows a lean meter
  (left/center/right counts) with a tick where an average story splits, and a 🙈 filter shows only blindspots.
- **Transcription: temporary failures retry.** Out-of-memory and network errors are no longer recorded as failures
  (they stopped every item for good on the first prod run); only a missing or unreadable file is. Transcription
  waits for the language model to unload first and skips the round if it can't. The test suite no longer calls the
  real language model (it was loading it onto the shared GPU mid-transcription).
- **More shows.** News outlets' own daily podcasts shown (Reuters World News, BBC Global News, WSJ What's News,
  Bloomberg News Now, Politico Playbook, The Economist's Intelligence, CNN 5 Things, the Guardian's Today in Focus,
  Morning Wire); more political YouTube channels shown (Pakman, Secular Talk, Brian Tyler Cohen, MeidasTouch, TYT,
  Adam Mockler, Timcast IRL, Benny Johnson, Ben Shapiro, Dan Bongino, Matt Walsh). Archived only: ABC News Update
  (hourly), NBC Top Story, Al Jazeera's The Take, Steven Crowder, Candace Owens and long-form talk (Rogan, Theo Von,
  Flagrant, Jimmy Dore, PBD, Pod Save America's channel). 72 sources, 37 shown.
- **Headline changes: junk prefixes.** A rank from a "most read" list ("4 , ") or a view counter ("114.7k views : ")
  before a headline is stripped when scraping and ignored when comparing versions, so a story moving from #4 to #2
  is no longer a "change".
- **Headline changes: how a rewrite changed.** The language model reads both versions side by side and says, in a few
  words, what the rewrite changed ("added the death toll"), cached once per change. "Plainer wording" / "reads as
  better news" notes show only when that side-by-side reading and the two versions' own scores agree on the
  direction; either alone was noise (identical headlines came out "plainer").
- **Backups every run.** Each run first takes an online copy of the database (newest 5 kept), besides the nightly
  copies (30 days).
- **Trending ranks by what's on front pages now.** "Trending in the news" ranks stories by the share of outlets
  carrying them on their front page right now, weighted by age the same way as the news-day sticker (full weight
  for 12 hours, then halving every 24), instead of every outlet that covered them in the last day. A story outlets
  have dropped falls down the list. Items show both counts: on front pages now, and in all.
- **Sagas are kept across days.** Sagas are saved (saga table, story.saga_id). Each hour, today's stories are merged
  with the last 7 days of saved stories, starting from the saved sagas, so a saga grows or merges but never loses a
  part. Linking now needs a shared distinctive *name* (a word outlets capitalize mid-sentence) rather than any
  distinctive word, and hyphenated words split ("UK-Iranian" carries "Iranian"). Checked on Oct 3-4: Cornell keeps
  all 4 parts; a false link ("Trump rally in Alabama" with "Ohio layoffs before Trump rally", via "rally") is gone.
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
