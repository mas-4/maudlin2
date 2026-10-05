# Methods log

Every change to how bignews.day collects or measures things, dated. A chart that crosses one of these dates should be
read with the change in mind. Newest first. Scores in the database carry `scored_by` (model plus a rubric hash) from
2026-10-03 on; earlier scores say `qwen3:8b rubric:pre-tracking`.

## 2026-10-05
- **Thresholds rechecked on the bigger embedding model (mxbai-embed-large).** Three measures still matched headlines
  with the small static model (potion-base-8M) at thresholds set by eye. Each was tested on the day's data:
  - *Sagas:* 118 pairs of saved stories sharing a name, judged by the 30B ("one running story?"): 8 were. Both
    models separate them equally well (AUC 0.965 and 0.963), so sagas stay on potion; the gate to the judge drops from
    0.58 to 0.54, which lets all 8 through instead of 6 (20 questions to the judge instead of 17).
  - *Wire share:* of a week's 339 outlet headlines sharing 70% of their words with an AP or Reuters headline, all of
    them copies when read, potion at 0.9 kept 258 (dropping copies such as "White Sox beat Guardians 3-0 in Game 1
    of ALDS"); mxbai at 0.85 keeps all 339. Now on mxbai at 0.85, after the word rule: 242 copies in the week's news
    headlines instead of 201.
  - *Curators:* 200 aggregator headlines (Google News, Drudge, RCP, Political Wire), each with its closest saved
    story, judged by the 30B ("same event?"): potion at 0.7 made 60 links, 46 right; mxbai at 0.8 makes 75, 60 right.
    The judge was strict (it called "Rasmussen no-hits Yankees… Rays win ALDS opener" a different event from the
    Rays' ALDS opener), so both are better than these numbers.
  If Ollama can't embed, wire share and curators fall back to potion at their old thresholds.
- **Narratives across days.** A narrative in one day's report (posts by many people telling one thing) is now
  compared with the narratives of the last 14 days: the three closest by meaning (mxbai, at least 0.7) are put to the
  bigger local model (Qwen3 30B-A3B), which says whether it is the same narrative told again (the same claim about the
  same people or event) or a different one. Linked days make a thread; Folklore cards show the earlier days a
  narrative was told and by how many people. The first two days (Oct 4, a six-hour report, and Oct 5) gave 3 threads
  out of 7 questions: the Nantucket air-ambulance search, Saquon Barkley's injury and a disputed Bills call.
- **On the radio (#159).** The hourly newscasts of NPR (NPR News Now) and ABC News (ABC News Update), which we
  already transcribe, are now split into their stories in the order they aired. The bigger local model (Qwen3 30B-A3B)
  reads each transcript with the list of the 40 stories most outlets had on their front pages at the nearest run,
  writes a short headline for each newscast story, and says which front-page story it is, if any (the same event, not
  the same topic). Splitting at reporters' sign-offs alone missed anchor-read items. ABC's ad wrapper (a promo before
  the anchor's "ABC News, I'm ...", a sponsor read after "This is ABC News") is cut off by that pattern first: the
  model's own ad calls were unsteady. A story is kept only if its first words occur in the transcript after the
  previous story's (once the model copied the front-page list as a newscast, reusing one real opening for all of
  them), and a story told twice is kept where it first aired. The page sets each hour's
  newscasts beside the front pages' biggest stories and counts how often a newscast led with their biggest one.
  Newscasts from before Oct 4, 13:05 UTC have no front-page snapshot to compare with and are left out.
- **Rumors stated the way their tellers state them.** The one-line summary of a fact-checked claim sometimes
  stated the fact-checker's correction instead of the rumor ("the video shows Muslim women queuing for a clothing sale,
  not free childcare"); 10 of the 80 in the motif index read that way, so motifs filed from them described the
  debunking, not the story. The summarizer is now told to state what the rumor's spreaders say is true, never the
  correction, and those claims were rewritten ("a video shows Muslim women queuing for free childcare"). Motif names
  follow the same rule: the story as told ("Caught on camera"), not the verdict ("Historical footage
  misattribution"); analysts' words like "narrative" and "controversy" were dropped from names.
- **Hand labels.** A headline checked by hand on our label-check page now carries the person's mood, loaded-wording
  and feelings labels in every measure (the model's where the person agreed), marked as hand labels so no rescore
  replaces them. Only a few dozen headlines, chosen evenly across the model's labels; they also measure the model: of
  the first 19, mood matched 11 (16 within one step, 1 opposite sign), loaded wording 14 (18 within one), feelings
  12. Of the 7 checked since the Oct 4 rescore: mood 5, loaded wording 6, feelings 7.
- **Motifs reused, and checked by hand.** Named one claim at a time without seeing the index, nearly every motif was
  a one-off (223 of 259 held a single claim), and the same name was coined as separate entries ("Blame shifting"
  four times; now merged). Now the model sees the 15 motifs closest to a claim before naming it, files it under one
  that fits, and coins a new name only for a shape none of them covers; a new name already in the index, word for
  word, is that motif. Re-filing 20 claims on a copy of the index, 17 found an existing motif (the old way, 1 of
  12), though some fits are loose while the index's names are young. A person checks filings one by one ("is this
  claim an instance of this motif?"); a no takes the claim out of that motif for good.
- **Motifs for political news, and cleaner names.** Folklore groups that are news reports or shared reactions
  got no motif, but news is powerful when it confirms a story people already tell (a Russian lab worker's plague
  death, retold as a bioweapon): political news is now filed in the motif index too. Non-political news, sports
  picks and shared topics aren't (a WNBA semifinal "prophecy" had become "Valkyries to defeat Aces"). Motif names
  over seven words are dropped: the model sometimes gave the claim's own sentence, or echoed its instructions, as a
  name. 25 such entries were removed from the index (10 from sports and moods, 15 sentence names), and their
  claims refiled where they had no other motif.
- **Names merged on the "mentioned:" filters.** The model names one subject several ways (Trump / Donald Trump,
  GOP / Republican Party, Supreme Court / Supreme Court of the United States); names now pass through aliases to
  one name, seeded for the common cases and curated by hand.
- **A saga taken apart by hand, and a saga tracker.** The 8B judge had joined an Energy Department employee's
  arrest for aiding the Houthis with the Yemeni offensive against them ("Yemen-Houthi military conflict"); the
  30B keeps them apart, and saved sagas never come apart on their own, so it was taken apart by hand (as the Iran
  plot saga was on Oct 4). A new Sagas tracker lists every saga kept, with each part's time on the front pages.
- **Sagas: a looser name rule and a bigger judge.** Two stories could become parts of one saga only if a name rare on
  the day was in 30% of both stories' headlines; the RAF Fairford bail story and the bombers-pulled-from-Fairford
  story (0.67 alike) never qualified, since "Fairford" was in 42% of one and 10% of the other. Now 30% of one and
  10% of the other is enough to ask the judge (6 more pairs over the week's 91 stories). The judge moves from the 8B,
  which called the Fairford pair "related cases but different outcomes", to the 30B. Two fixes were needed before
  it could be trusted. Cut off mid-reason, or answering a bare true/false, it said no after reasoning its way to "the
  same developing story" (Cornell); it now finishes its reason and answers in words. And the second wording asked
  about a story "followed over time", which two groups on the same development aren't (it called FlyDubai
  "redundant"); it now counts the same development and later developments alike. On 14 hand-labeled pairs, 13 agree; the
  14th (an Energy Department arrest and the Yemen campaign, which the 8B had joined) it keeps apart, which we think is
  right. Sagas already saved don't come apart. First new sagas: the Fairford plot, and Alito's remarks (retirement,
  intimidation of the Court).
- **Reuters and AP titles lose Google's source tag.** We read both through Google News, which tags each title with
  the outlet; we removed the tag as a name (" - AP News") but Google has lately tagged by domain as well
  (" - apnews.com", " - reuters.com"), switching back and forth for the same article: 306 of the 364 Reuters and AP
  articles stored with more than one title in the last three days differed only by the tag (all but 8 were already
  ignored as minor rewrites). Both forms are now removed as headlines come in. The tag had made "AP News" a name
  in AP's stories on the "mentioned:" filters; names are now checked against headlines without it.
- **Quotes inside one another count once.** Outlets often cut the same quote differently ("Bad Things", "world
  should accept some bad things", "We Should Accept Some Bad Things Happening For The Benefits"); as separate chips
  they filled a story card with one quote and pushed other quotes past the four-chip limit (7 of 28 cards with
  quotes this morning). A quoted phrase that sits inside another, whole words, now joins it: one chip counting every
  outlet that used any of the wordings, shown as the wording most of them used (the longer on a tie), the others in
  its tooltip.
- **Stories by who and what they name.** The local model names the people, countries, places, organizations and
  groups each current story is about (up to six, by their common short names, remembered per story). A name is kept
  only if the story's headlines actually contain it (asked about an OPEC+ story, the model added Russia, Iran and
  Iraq), and the United States is left out (nearly every story is about it). Names in two or more current stories
  become "about:" filters over the story cards (renamed "mentioned:" the same day: often a story only mentions the
  name). Not sagas: these are unrelated stories that name the same subject.
- **Our own motif index replaces Thompson's chapters.** Thompson's Motif-Index is built from folktales and fits modern
  political rumor poorly, so the site no longer shows it. Instead we build our own: each folklore narrative and each
  fact-checked claim gets one to three motif names from the model (reusable framings, no names or dates, two-sided
  when contested), and each is filed under the closest existing entry the model judges the same shape (candidates at
  0.7+ similarity, forced choice with "new"), or starts a new entry (M001, M002…). The naming and matching go to the
  bigger local model (qwen3:30b-a3b); a person merges, renames and deletes entries in an organizer on the label-check
  page, which suggests merges by name similarity. First fills, with the 8B and one motif per claim: at 0.6 vague
  early entries snowballed (one took 16 unrelated claims); at 0.76 almost nothing merged (111 motifs from 115
  claims), and the 8B still made absurd matches (a tax-vote claim filed with a harassment story). Folklore,
  Rumors and the Motif index now share their own "folklore" menu.
- **Gap: no runs from 3:04 to 7:10 AM Eastern.** The desktop's idle timer suspended the machine during the 3 AM
  run's GPU transcription (which had grown to its full 10 minutes with the new call-in and podcast feeds); it never
  resumed, so the 4, 5 and 6 AM runs and the nightly folklore report were lost until a cold boot at 7:10.
  Headlines live on front pages only during those hours are missing. Fix: each run holds the desktop's sleep lock
  until it's done, and a missed nightly report is made up by the next run after 4 AM.

## 2026-10-04
- **Mood rescore done** (8:22 PM; 20,378 stored headlines plus 1,441 that arrived during the run). Over 15,425 news
  headlines, 79% kept the same mood and 1.1% flipped sign; all leans read grimmer, right-leaning outlets most
  (average mood -0.60 to -0.76; left -0.50 to -0.62; center -0.29 to -0.39; RedState -0.78 to -1.06), as expected
  once a headline's own dismay counts. Spin: 77% the same; right-leaning outlets' average rose (0.65 to 0.72) from
  counting outrage bait, the others held or dipped. Old scores: data/archive/scores-before-rescore.csv.
- **Rumors: are they circulating?** Each fact-checked claim is looked for nightly in the last 72 hours of our
  Bluesky and Mastodon sample: posts at least 0.72 alike by meaning are candidates, and the model reads up to 12 one
  at a time, saying whether each is telling the claim, arguing against it (sharing the fact-check counts), only
  about the news around it, or something else. The Rumors page shows counts of people, never posts. Stance matters
  here (unlike for a story's shape): the closest posts are often people sharing the fact-check or the news report
  itself. First look (half a day of sample, 66,722 posts): 15 of 91 claims seen. Weak spots: some fact-checker
  items are explainers of real news, so "telling it" is people sharing news; single posts can be misjudged.
- **Beyond the front pages.** The front page's "Investigations" and "On the shows" link lists are gone (we're not an
  aggregator): each piece now shows on the story it covers (🕵️ investigated by, 🎙️ on the shows), and a new page
  lists what the shows, newsletters, streams and investigative desks discuss, tagged by subject by the local model
  (one to three from a fixed list of 35), plus a directory of all 121 sources beyond the front pages and what we do
  with each. Subject tags pad: asked for one to three, the model gives two or three even for teaser titles; asking
  for one unless others are plainly discussed only partly helps.
- **Conspiracy scope held back.** Even asked first whether a secret plot is claimed, the 8B model called 43 of 94
  fact-checked claims conspiracies (e.g. "Jon Husted pushed for data centers and tax incentives"). The scope shows
  only in local previews until a confidence cascade (the model's own answer probabilities, with unsure answers sent
  to a bigger local model) is calibrated against hand checks. Rumor class and subject stay on the site.
- **Rumor shapes: three open label sets, and a Rumors page.** Thompson's index fits folktales, not modern political
  rumor: in a blind test (151 claims: folklore narratives and fact-checked claims; up to 16 candidate entries each
  by meaning), the local 8B model picked a motif for 30 of its first 53 claims and the user accepted 1 of 6 checked;
  a strong model (Claude, in-session) picked 5 of 151, and the user accepted both checked. Specific motifs stay off
  the site. Instead every narrative and fact-checked claim gets three short labels from the study of rumor,
  concepts rather than anyone's text: rumor class by what drives it (wish, dread, wedge; Knapp 1944, DiFonzo and
  Bordia 2007), conspiracy scope (event, systemic, superconspiracy; Barkun 2003), and a subject family (our own
  list, after the chapters of urban-legend collections). The new Rumors tracker lists the fact-checkers' recent
  work with these labels, filterable; verdicts are always the fact-checkers' own, behind their links. Survey of
  other schemes (SemEval 2025 Task 10 narratives and roles, UK election narratives, EIP, Brunvand, ATU, Berezkin,
  EUvsDisinfo, NewsGuard and more, with their licenses) on #145.
- **Narrative labels from one point of view, and only when most posts are about it.** The labeler now names the claim
  most posts share (one or two posts' claim isn't the narrative), says for each part (villain, victim, hero)
  whether the story has one before naming it (it used to fill every part: "hero: the Bills"), and casts parts and
  side from the tellers' point of view. Each narrative's sampled posts are then asked one by one whether they're
  about its claim (telling it or arguing over it alike); under half, it's not counted. On the side: the model's
  guess is unchecked (it called trans people's own posts "right"), so the site shows a side only from evidence,
  the AllSides lean of outlets whose articles the posts share (two or more rated shares); the guess shows only in
  local previews. News reactions get no cast or motif. Re-run on the flagged groups: the Jets penalty and the
  trans group's misreading are fixed; perspective still sometimes mixes ("Canadians in Florida").
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
