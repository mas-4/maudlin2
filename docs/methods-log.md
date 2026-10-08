# Methods log

Every change to how bignews.day collects or measures things, dated. A chart that crosses one of these dates should be
read with the change in mind. Newest first. Scores in the database carry `scored_by` (model plus a rubric hash) from
2026-10-03 on; earlier scores say `qwen3:8b rubric:pre-tracking`.

## 2026-10-08
- **"Kind of" is now "rests on".** The one link that ranks motifs, until now "X is a kind of Y", now reads "X rests on
  Y": X only makes sense given Y, as a kind of it, or as a case, argument or figure by which it's told ("Magic money
  tree", an argument, rests on "Politicians' empty promises", a theory). Every kind-of link still holds as one; a survey
  of the 83 found about 18 that had only ever been right this way (an archetype or argument resting on a theory). The
  rule of Oct 7 that the link stays within one genre is gone, and the links it took away are proposed back. The
  proposer, its judge, the workbench, both maps and the export say "rests on"; the data is unchanged.
- **How sure a filing is.** Each claim the model files under a motif now gets a fit: the chance the person keeps it,
  from a small model trained on their own decisions (723 so far: 572 filings kept, 151 taken out). It weighs how
  alike the claim and motif are (the filing shortlist's measures, the claim held out), how the motif ranks among all
  motifs for the claim, how many motifs the claim is in, where it came from, and whether the person has curated the
  motif. Tested with each claim held out: AUC 0.83 (the shortlist's score alone: 0.74); at a fit of 85% or more it
  passes 64% of the filings the person kept, and 95% of what it passes they kept. The check list goes likeliest
  first, and the filings over that line can be passed in one step, except a filing in a motif made for that claim
  alone, or from a source with fewer than 30 of the person's decisions (the shows, for now). Not used on the public
  site: what's public is still only what the person has checked.
  Later the same morning, on the person's word: only filings in their own motifs (marked done) get a fit or are
  learned from; a motif the model made and nobody has shaped measures nothing (a claim had scored 100% in the motif
  just named from it). Retrained so: AUC 0.82, sure from 95%, where 96% of passes were kept.
  By midday the fit weighs many more kinds of evidence (app/analysis/motif_signals.py): the motif's note alone, its
  keywords, the claim rewritten as the bare shape of its story, the motifs of the most similar filed claims, a second
  embedding model, the person's groups, a cross-encoder reranker (Qwen3-Reranker-0.6B) and the filing model's own yes or
  no with its probability. Tested on 749 of the person's decisions held out by claim: AUC 0.885; at a fit of 85% or
  more it passes 76% of the filings they kept, 95% of what it passes kept (29% at that precision the morning before).
  Boosted trees did no better than the plain weighting, and both level off by half the decisions: more checking alone
  won't move it much. Fits are worked out in the hourly run and kept on the filings. The person's confirmed filings get
  one too: the lowest of the model's own, a second look for a hurried yes.
  In the afternoon, from the first experiments (docs/filing-experiments.md), one more: the claim against each motif's
  note and nearest claim with the day's news taken out. The main directions the latest 6,000 headlines vary along are
  mostly topic (a country, a storm, a trial); projected away from both sides, what's left leans to how a story is told.
  Held out, it brought 1.3 points more of the person's motifs into the top 12, with nothing of their filings in it to
  leak. The directions are worked out once a day.
- **New motifs come with the model's note, genre and groups.** A motif the model makes for a claim no motif fits used
  to arrive bare: no note until it held three claims, no genre or group until the person gave one. Now the hourly run
  drafts all three straight away: the note from its name (the claims only to see how it's told), the genre judged
  against examples of the person's own motifs in each genre, and up to two groups, each the model's yes among the three
  groups whose motifs are nearest. The genre and groups are marked as the model's guesses (🤖 in the checker) until the
  person marks the motif done or sets them by hand; till then nothing learns from them (genre examples, group centers,
  the group signal of the filing model and the public pages read only the person's), and a merge leaves them behind.
- **Fact-check claims read from the piece, not the headline.** The person often opened a fact-check to see what was
  actually claimed, so their filing rested on more than the one line the models saw. Each fact-check's own text is now
  kept (app/analysis/factcheck_text.py): from the feed where it carries the whole piece (PolitiFact, FactCheck.org,
  Lead Stories, NewsGuard), otherwise read from the page, 20 seconds apart per site, at most 24 pages a run, robots.txt
  obeyed (read under our own name: the sites block named AI crawlers, not readers like us). The labeler reads the
  piece's opening and gives the claim as its tellers state it, who says it and where, plus two or three sentences of
  what the piece shows; the person's own corrections of claims (46 so far) are shown to it as examples. A claim
  already filed keeps its wording (the reading from the piece is kept beside it), so nothing filed changes under the
  person. The checker's 'where it came from' shows the piece's reading and its opening.
- **Five podcasts' episodes were being dropped since Oct 4; six video channels had moved.** A health check of the
  side feeds found The Daily, the Brian Lehrer Show, the Megyn Kelly Show, WSJ What's News and NBC's Top Story with
  nothing new in four days: their feeds had begun giving every episode the show's own page as its link, so each new
  episode looked already stored. An episode whose link another shares is now told apart by its guid. The YouTube feeds
  of the Young Turks, Timcast IRL, Benny Johnson, Matt Walsh, Candace Owens and Destiny pointed at channels gone quiet
  (some for a year); each now follows the channel its handle names. Dan Bongino's and Flagrant's channels have posted
  nothing since 2025 and early 2024: dropped, their podcasts carry them. The 145 outlets' front pages and every hourly
  run of the last day were fine.
  So it doesn't happen silently again, each hourly run now checks that every outlet was seen on its front page in the
  last six hours and that every feed that posts regularly has something new within four times its usual gap (three
  days at least), and that no feed is stuck with a handful of items; what isn't is a warning in the log and a 🩺 box
  on the checker's 📊 tab (app/health.py).
- **Weak fits come with where else they might go.** The person's time is better spent correcting weak filings than
  hunting for motifs: for each claim with a filing the confidence model gives under 50% (one nobody has checked, or one
  they confirmed that's up for a second look), the hourly run scores the twelve of their motifs the shortlist ranks
  highest that the claim isn't in, and keeps the best three from 30% up. The checker shows them under the claim ("might
  fit better") and under each second-look row: ＋ files it there too, ✕ says it isn't that motif (never suggested
  again).
- **Top stories as full cards again.** The front page's nine top stories (ranked as before) are the stories page's
  own cards again, every outlet's headline on each, the lighter cards of Oct 6 having read as boring. Each keeps a bar
  of who carries it by lean, now in five bands (left, leans left, center, leans right, right, plus unrated) instead
  of three, so a story carried by the far left reads apart from one carried by the center-left.
- **Folklore and Rumors are one page.** Folklore and rumors (folklore.html) is now one catalog of what's told, from
  three places, each marked on its card and filterable: retold online (Bluesky and Mastodon, as before), told on the
  shows (a claim told on two or more of the shows we transcribe, or by two or more callers: which shows, how many
  callers, the tellings by the shows' lean; never the quotes or who called), and fact-checked (the old Rumors page;
  a check already linked from a narrative's card isn't repeated). The model's built-in genre (conspiracy theory,
  contemporary legend…) is gone from the cards: a card's genres are now those a person gave the motifs it's filed
  under. rumors.html sends visitors to the fact-checks.

## 2026-10-07
- **Claims from the shows we transcribe.** What people post (Bluesky and Mastodon) leans left, so the folklore page
  heard little of what's told on the right. Every podcast, call-in show and video show we transcribe (about 400
  episodes a week: 157 right, 132 center, 105 left) is now read for the claims told on it, by the same model and
  checks as the focus groups: each claim's quote must be in the transcript and support it, and each says who told it
  (host, guest, caller, a played clip). A claim reaches the motif index only once it's told on two shows or by two
  callers: one host's take isn't folklore; told again elsewhere, it is. Quotes and callers stay off the site.
- **A better shortlist for filing claims.** Filing a claim, the model chooses among the motifs most like it; when the
  motif a person would have chosen wasn't among them, they added it by hand (over 200 times). The shortlist was the
  8 closest by one measure. Now several measures of likeness (the motif's description, its nearest claim, the center
  of its claims, its size, its neighbours in the kind-of tree) are weighed by a small model trained each day on the
  person's own confirmed filings, and a shortlisted motif brings its broader motif and its kinds along (about 12
  shown). Re-filing all 372 confirmed claims, each kept out of what it was tested against: the model found 375 of the
  763 motifs the person had them in (322 before), 47 of the 206 they had added by hand (33), with no more picks the
  person had taken out (16 both ways).
- **Proposals sorted by how likely they're approved.** About half the model's kind-of and related proposals were
  rejected. A second read by the same model, asked how likely the person was to accept each one, was little help
  alone: it gave most approved and rejected proposals the same 2 or 3 (and a first prompt that called the person
  strict rejected nearly everything). Weighed together with plain facts about the two motifs by a small model trained
  on the person's 144 decisions, it does better: tested on decisions it hadn't seen, the least likely tenth of the
  approved marked a line below which fell 29 of 65 rejected. The checklist is sorted by that chance, and those below
  the line are folded at the bottom, ticked, for the person to skim and reject at once; nothing is hidden.
- **The public motif map looks like the working one.** The site's map was drawn once (Oct 6) and missed a day of
  layout work on the checker's map. Both now draw through one script (static/motif-map-layout.js): each group placed
  on a ring of its own, links out of a group pulling weakly, a group drawn as a blob around its members with
  non-members kept out, a dot's fill its genre and its outline its place in the kinds, and one color per group and
  genre on every page. The site shows genres only once a checked motif has one. Editing stays on the checker.
- **A motif a person made and wrote a note for is done.** Marking it done was a second step after writing the note,
  and 92 motifs the person had made (or renamed) and described sat unmarked, off the site. Now saving a note of
  theirs (or keeping the model's draft) on such a motif marks it done, with the claims it holds then; one they unmark
  stays unmarked. The 92 were marked done: 332 motifs on the site, 741 claims (each claim still read for named
  accusations first). A model's motif with no person's name on it still waits for a person.
- **A merge keeps everything.** Merging one motif into another moved its claims, related links and kinds, but lost its
  own broader motifs, its groups, its genre, its note and the person's "not the same" verdicts, and its claims seen
  when it was marked done showed as new again. Now all of it comes along (a broader motif only where it can't make the
  motif a kind of itself; the note and genre only where the motif kept has none).
- **A claim a person checked counts as seen.** A motif reaches the site once a person marks it done, with the claims it
  held then; claims filed since waited, marked new, until it was marked done again, even ones the person had checked
  ✓ one by one in the meantime. A claim checked ✓ or filed by hand now counts as seen: no longer new, and shown with
  its motif. The model's own filings since still wait. 554 claims show on the site instead of 431; motifs marked new
  went from 99 to 34. (The checker's organizer and singles pages were dropped too; the workbench does their work.)
- **A correction proposer for the motif index.** gemma4:26b reads over the motifs and proposes small fixes, each one
  change a person approves or rejects in the workbench's 💡 proposals checklist: a typo in a name or scope note (only a
  small edit counts, not a rewrite), one motif a kind of another, two related, two the same motif (merge), a motif
  into one of the person's groups. Candidates are found cheaply first (motifs alike in meaning, motifs sharing a claim,
  motifs near a group's members) and only those put to the model. Approving runs the person's own action (logged,
  undoable); a decision is kept, so a rejected proposal never comes back, and one overtaken by hand drops out. It runs
  once a day from the 5 AM hourly run on (never in the run that makes the narrative report, which nears its
  45-minute limit), at most eight minutes, going on in the next run if cut short. The model's own "no" and its typo
  reading are kept with a mark of the motifs as they were (name, note, about how many claims), so a motif that
  changes is looked at again. It also reviews the links already made (related, kind of): one the model calls unrelated
  comes up as a proposal to take it away, and one it keeps isn't read again until either motif changes.
- **No more villain.** The folklore labeller named who each narrative casts as the villain (Propp's part), and its
  picks were too often wrong to show. It no longer asks, and the Folklore page, the checker and the reports leave the
  part out, old reports included; the victim and the hero stay. Fact-checks' labels still carry a villain field,
  unused and never shown (rewording that prompt would relabel every fact-check and the claims filed from them).
- **A story back on the front pages stays one story.** A news cluster continues the saved story that holds most of its
  headlines; one that left the front pages and came back hours later under fresh headlines shared none, and became a
  new story. The physics Nobel was on one noon run on Oct 6, gone, and back at 5 PM as a second story: a saga of two
  near-identical parts. Now a cluster that continues no story is compared with the stories that left the front pages
  in the last 48 hours; one sharing two of its frequent words is put to gemma4:26b: the same news event told again,
  or a different one (the next game of a series, a new ruling, an arrest after a crime)? The same event continues
  the old story. On the 42 pairs the rule would have asked about in the week before, it joined only the Nobel pair
  (the first wording refused it over one stray headline about the medicine prize; it now goes by most headlines).
  The two Nobel stories were merged by hand; a merged story's page redirects to the one kept, and TV, radio and
  narrative links to it follow.
- **Narratives linked to news stories by the bigger model.** Which front-page story a retold narrative is about (its
  card on Folklore, and where it shows on story and saga pages) was asked of qwen3:8b, which put "Jacob Geller is a
  rapist…" on the Cornell rape case and the threats against the Cornell accuser on a different part of the saga. Asked
  again of gemma4:26b, the 346 links it had made differed on 42; read by hand, Gemma was right on about 25 of them and
  the small model on about 11, and Gemma joined fewer wrongly (5 to 7) and missed far fewer (3 to about 20). From
  tonight's report on; earlier reports keep their links.

## 2026-10-06
- **Named people accused of crimes.** An outside reader found the motif index, a story page and a saga page showing
  "Jacob Geller is a rapist who has avoided accountability…", retold by eight people online: an unverified accusation of
  a serious crime against someone named who holds no public office. Now every claim the site shows from people online
  or from voters (motifs, folklore, story and saga pages) is first read by gemma4:26b: does it say a person it names
  committed a crime or abuse? Officials, candidates and household names stay named, and so does anyone our outlets'
  front-page headlines have named in three or more articles (the model didn't know Howard Lutnick is in the cabinet).
  Anyone else is replaced by who they are ("A YouTuber is a rapist…"), and their posts, cast and earlier tellings
  aren't shown with it; a claim whose name can't be swapped out cleanly, or that hasn't been read yet, isn't shown.
  Fact-checkers' claims are shown as written. Two hand-kept lists override the model: names never shown
  (`never_named.json`) and names always shown (`always_named.json`). Story and saga pages also show a claim found
  twice in one night's report, in nearly the same words, once.
- **A lighter front page.** The front page had become a dashboard, a corpus and a reader at once (an outside reader
  counted 36 links on one story card). The story cards, every outlet's headline on each, moved to their own page,
  Every story (stories.html). The front page keeps the cloud and puts the nine hottest stories (ranked as before) in
  short cards, each with three things: how its coverage spreads across the lean scale, one framing contrast (a phrase
  only one side uses, skipping phrases made only of the story's title words, or the most-quoted phrase), and one sign
  from beyond the front pages (TV, radio, people retelling it, a fact-check). Sagas follow, then the trend boxes. Each
  saga has a page of its own (saga-<id>.html) following it across its parts.
- **Sagas: no more joining by persistence.** An outside reader found three sagas holding a part from another
  storyline. All three were the old judge's yeses, and one shows the flaw: the Supreme Court climate case and an
  overview of the court's new term were judged separate 25 times, then joined on the 26th, because each hour the
  stories had new headlines, so a new sample to ask about, and one yes was kept for good. Now a verdict is kept for the
  pair of stories (`saga_pairs.json`) and never asked again; the judge sees each story's most central headlines, not
  ones spread evenly across it (stray headlines from a neighbouring storyline had stood in for a story); and a newcomer
  is judged against the saga's part nearest to it. The judge's wording now says that different angles on one event,
  its consequences and reactions are one story, and that a different focus is no reason for "separate": on the 46
  labeled pairs it found 7 of the 11 true running stories (5 before) and still joined none wrongly. The three wrong
  parts were detached (the Nebraska rally from the diesel order, the court's new term from the climate case, two
  Iranians charged over a plot against Jews from the RAF Fairford bombers story); two sagas ended. A check of every
  saga against this judge would also have split four borderline ones (Alito's two stories, the Saudi-Houthi fighting,
  Paxton's campaign, measles in two states) and one clear one (two headlines on one Ohio rally); those were left as they
  are, for a person to judge.
- **Each narrative keeps all its posts.** The nightly report now keeps the private keys of every post in each
  narrative, not only ten sample texts, so a person checking a claim sees everything it was found in. The texts stay
  in the post store under its 30-day limit (a deleted post is gone from it too); the reports of Oct 4-6 had their keys
  rebuilt by grouping their posts again (361 of 367 narratives matched).
- **Jubilee's Surrounded, transcribed.** Jubilee's weekly Surrounded (one guest against 20-25 people who disagree
  with them) joins The Focus Group and the call-ins as ordinary people speaking for themselves: archived from its
  podcast feed and transcribed on our GPU in the same tier, for research. Its Middle Ground has no audio feed, and its
  YouTube feed is now mostly short clips of its commentary show, so neither is followed.
- **The nav follows a story downstream.** Two links (every story, sagas) and four menus in the order a story travels:
  📰 front pages (every headline, outlets, headline changes, emotions, who's in the news, the Supreme Court, the
  archive), 📡 on air (TV, radio, shows and newsletters), 🧶 online (folklore, rumors, the motif index) and 🛠️ how it
  works (now with the methods log, which wasn't in the nav). The old grab-bag "trackers" menu is gone.
- **Scope-note drafts by Gemma 4 26B.** A motif's draft note is now written by gemma4:26b, not qwen3:30b-a3b, after
  drafting notes for the 49 motifs whose notes the person wrote and comparing them with theirs: Gemma's were closer in
  meaning (0.73 against 0.71) and told the kind of story where the 30B restated a single claim, and the 30B gave up on
  10. A draft that opens with the motif's own name ("Breaking ranks occurs when...", half of Gemma's) is asked again.
- **Narrative threads judged by Gemma 4 26B.** Whether a narrative told today is one told on an earlier day is now
  asked of gemma4:26b, not qwen3:30b-a3b, after a test on the 32 pairs the live code had asked about (labeled by
  Claude): Gemma found 18 of 21 retellings in both runs and wrongly joined 1 of 9; the 30B found 15 and 17, missing
  plain repeats (the same Nobel prize, Sánchez's snap election). The threads were rebuilt from the three daily reports
  with it: 17 narratives told on two or more days (was 16).
- **New motif names matched more often to the motifs already there.** When the filing judge names a new motif, its
  name is first checked against existing ones, but only those at least 0.7 alike by meaning were offered to the model.
  Tested against the person's merges: the motif a duplicate was later merged into reached the model for only 7 of 31.
  At 0.6 it reaches it for 20, and the model found 14 (against 7), joining 2 of 26 pairs the person had said were not
  the same (against 1 of 11). The floor is now 0.6; the model stays (gemma4:26b, gemma4:12b and qwen3:8b did no better).
- **Widely seen Bluesky posts, embedded.** Until now no post was ever shown, only the model's summary of what a
  narrative's posts share. Now each narrative can show up to two of its own Bluesky posts that were already widely
  seen: 25+ likes, reposts, quotes and replies together, or 3+ from an account with 5,000+ followers (Bluesky gives no
  view counts). They're embedded with Bluesky's own embed, never copied, so a post its author deletes disappears from
  our pages, and shown posts are looked up again every six hours. Never shown: anyone who has asked Bluesky not to
  show their posts to logged-out visitors (one in five of the posts in a test sample), accounts labeled bots, posts or
  accounts with a moderation label, and anything from Mastodon. To do this the sampler now keeps each Bluesky post's
  address (at://...) with its text, under the same 30-day limit; the nightly report keeps the 20 posts closest to
  each narrative's claim; each hourly build looks a few batches up on Bluesky's public API (at most 8 calls, 10 s
  apart). The thresholds are a first guess, to check against the first nights' counts.
- **Story pages: a week of retellings, later fact-checks, and voters.** A story page showed retellings only from the
  latest nightly report, tied by the story's label (which gets reworded), and fact-checks only if they were found while
  the story was on a front-page card: 3 of 160 pages had any. Now each day's last report of the week is read; its
  story links are tied by id (saved from Oct 6 on), or by the same label, or by the label of the story around then that
  shares at least half its words; a narrative told on several days shows once, on its latest day (51 stories have
  retellings, up from 37). Fact-checks are matched for every story of the week at build time, in their own cache, so
  one that came after the story left the front page still appears. And a new card, "the same shape, told by voters",
  lists what Focus Group voters told that's filed under the same verified motifs as the story's retellings, in our
  words, with the episode: the first place motifs connect a story to other material.
- **The motif index can be exported.** The workbench's 📦 export (and `scripts/export_motifs.py`) writes the index as
  a readable catalog (Markdown), a spreadsheet (a row per claim), JSON, or SKOS in Turtle for the planned mapping to
  prior catalogs (docs/motif-catalogs.md). By default only verified motifs, with the claims they held when verified
  and only a person's notes, the same as the site; "everything" adds unverified motifs and marks draft notes.
- **One-sided wording: the story's own words don't count.** "Only the right says 'bakker dead'" was on the front page
  while the left wrote "Bakker dies": a phrase one side used, but not a framing. A phrase now counts only if at least
  one of its words (stemmed, with dead/death/dies folded together) never appears in the other side's headlines on the
  story. On three days of stories this dropped 39 of 101 phrases, mostly vocabulary ("federal judge", "former rep",
  "terror plot" against "terrorism plot"); "killed" and "died" are kept apart, since that choice is framing.
- **Word cloud: no made-up words.** The cloud folds plurals to their singular, and the folding turned "dies" into "dy"
  (WordNet's -ies rule), so on Oct 6 a word "dy" gathered every death story of the day (Jim Bakker, Dennis Hastert, the
  Kenya Ebola case). Now the cloud picks nouns before folding, never folds to a word of two letters or fewer, leaves
  words in -ics alone, and drops "dies". On the day's 10,477 headlines this also took out verbs that had passed as
  nouns ("calls", "plans", "vows", "warns") and two more mangled words ("leaves" as "leaf", "discusses" as "discus");
  the top 25 words didn't change. Also: the top word is sized against the runner-up, not the smallest word, so it no
  longer dwarfs the cloud, and on a phone it's no longer dropped for lack of room.
- **One claim, told several ways.** A person can now say two claims in the motif index are the same claim: the one
  folds into the other in every motif either was in, its words kept as a variant of the kept claim, and a later
  telling in exactly those words is filed as the kept claim, not as a new one. A motif's claim count then counts
  claims, not wordings.
- **Outlet chips: the face is the headline's feeling.** Each outlet's chip on a story card showed 😠 for any headline
  whose mood was below zero, a leftover from the 2024 site, so nearly every chip looked angry, even on obituaries
  whose headlines were mostly sad. It now shows the headline's own strongest feeling (😱 fear, 🤬 anger, 😭 sadness…;
  none when neutral). Its mood is compared with the other outlets' headlines on the story (it had included itself),
  and when they agree the tooltip says "same mood as the other outlets" instead of "+0.00". Most outlets do agree:
  mood is a five-step scale, and the same event usually gets the same step. Found by an outside reader.
- **Only verified motifs on the site.** The motif index grows with the model's filings, but the site now shows a
  motif only once a person has looked over its claims and marked it done, and shows only the claims they saw then;
  claims filed since wait until they mark it done again. Unchecked motifs stay in the index and in the curation tools.
  On Oct 6, 234 of 261 motifs had been marked done.
- **Sagas: the judge is Gemma 4 26B.** On 46 pairs of stories labeled by hand (11 of them one running story), it agreed
  on 40, joined none wrongly and took 2 seconds a pair; Qwen3 30B-A3B agreed on 41 but joined one pair wrongly and took
  33 seconds. Gemma finds a few fewer true parts (5 of the 11 against 7), so a saga may gain a part an hour or two later
  than before, but a wrong join, the kind a person has had to veto, is rarer. Verdicts already cached are kept.
- **Focus Group: a claim must be what its quote says.** Since Oct 5 a voter claim's quote had to be in the transcript,
  but nothing checked that the quote said the claim: "Politicians cheat on their spouses but still get elected" was kept
  with a quote about politicians telling you what you want to hear, and filed in the motif index. Now Gemma 4 26B is
  asked whether the quote is evidence for the claim (the voter says it, or a central part of it, in any words), and a
  claim it isn't evidence for is dropped (kept on record with the reason). A first wording ("does it support the claim
  as worded?") passed only 6 of 16 sound claims; the one in use passed 14 of 16, turning down two that added what the
  voter didn't say, and still caught the bad ones. Claims read before were checked the same way, in the wording a
  person had corrected them to: 26 of 231 were dropped (one said a voter praised a governor the voter had said was
  "not my favorite") and taken out of the motif index.
- **Transcripts: names Whisper mishears.** 35 of 46 mentions of AIPAC in our podcast and Focus Group transcripts had
  come out as "APEC" or "APAC", and Hegseth and Whatley were misspelled too. Whisper now gets a list of names and terms
  to expect (fixed ones such as AIPAC, Hegseth, MSNOW, and the 50 most-named people and groups in recent stories), and
  known mishearings are corrected after transcription, sentence by sentence and only where it's safe: APEC is left alone
  in a sentence about the Asia-Pacific summit, and "a PAC" is never touched. The same corrections were applied to the
  transcripts already made (14 changed) and to the Focus Group claims drawn from them (10), five of which were already in
  the motif index and were corrected there through its record of corrected wording.
- **Focus Group and radio running order on Gemma 4 26B.** Each tested on its own work: on 10 newscasts, Gemma's stories
  passed the first-words check 96% of the time (Qwen3 30B-A3B 81%) with nearly the same front-page picks; on 12 Focus
  Group transcript parts every model's quotes were found in the transcript, but Gemma's claims were the voters' own,
  each with the voter's side, where Qwen3 30B-A3B took a host's analysis for a voter's.
- **Story pages: following a story downstream.** Every saved story seen in the last week has a page, and its card on
  the front page links to it. The page follows the story as it spread and changed: the first front page to carry it
  (a headline first seen before the story began is left out: it joined later), its peak, its first minute on TV and on
  the radio, the day people were found retelling it; then the front pages over time with the aggregators linking it,
  the phrases outlets quoted and the wording only one side used; TV minutes by channel and the captions; the radio
  newscasts and its place in each; the shows, investigators and satire on it; what people retell and the names in it;
  the fact-checks; and the saga it belongs to. Each run's findings around a story are kept (story_extras.json), so its
  page keeps them after it leaves the front page. Every link is made by our tools and can be wrong. Charts: how many
  front pages carried it at each hourly run, by lean (an outlet counts while one of its headlines on the story was on
  its front page, within half an hour of the run); and who carried it when, a bar per headline from when we first saw
  it to when we last did, with its TV captions, radio newscasts and the day it was retold online beneath.
- **TV and radio on the story cards.** Each card shows its minutes on screen on each news channel and the hourly
  newscasts that carried it in the last day (and how many led with it).
- **On TV.** The captions along the bottom of the screen (chyrons) on CNN, Fox News, MSNOW and BBC News, as the
  Internet Archive's TV News Archive reads them by OCR about once a minute (its "Third Eye" service, running since
  2017), with how many seconds each stayed up. One request a run; each day is kept as sent. The OCR is noisy ("NICOI I E
  WAL ACE DRECENTS" for the program title Nicolle Wallace Presents), and a line often runs a headline and a guest's
  name together, so lines are split, the clock and logos set aside, near-identical lines grouped, and a local model
  (Gemma 4 12B) says what each is (headline, name, promo, ad, junk) and corrects headlines and names for OCR errors only,
  with the program and the day's story labels as context. On a test batch Gemma 4 12B invented nothing; Gemma 4 26B
  "corrected" a steel plant in Iowa to Ohio and Qwen3 8B kept garbled promos as headlines. Each headline is matched by
  meaning to the stories on the front pages at the nearest run; the page shows each story's minutes on each channel
  beside its front-page rank, and each hour's longest-running captions.
- **Motif filing upgraded.** Claims are now filed by Gemma 4 26B judging the 8 closest motifs side by side (each by its
  name, scope note and three of its claims): which of them, none to three, is the claim clearly an instance of? Only
  when none fits is it asked, separately, whether the claim tells a recurring story worth a new motif; a plain report
  gets none. Tested on 60 of a person's settled filings, each held out: the old method (pick or name from the 15
  closest, Qwen3 30B-A3B) chose their motif for 37%; the new one 53% on the current index (65% on the bake-off's
  candidates, with 66% of its picks theirs). Asking for a new name in the same call as the judging cost several points,
  so the two are separate questions. Which model does which job, and how each was tested: docs/models.md.

## 2026-10-05
- **Choosing motifs, tested against a person's own filings.** The 160 claims a person had settled on the motif board
  (each held out of the index in turn) were filed by the live method (the 15 closest motifs by name and claims, one
  pick-or-name call to Qwen3 30B-A3B) and by a new one (three de-named "shapes" per claim, candidates found by shape,
  a yes/no check on each of six). The live method picked the person's motif for 37% of claims, 52% of its picks theirs;
  the new one 47%, but only 28% of its picks theirs. Finding candidates by shape was the weak part: the person's motif
  was among the 6 closest by shape for 58% of claims, by the claim's own words 74% (82% of the closest 10). Shapes stay
  out. A third design, the 8 closest motifs by the claim's words judged side by side in one call ("which of these, none
  to three, is the claim clearly an instance of?"), was then run with seven local models on 60 of the claims (the
  person's motif among the 8 for 46 of them, so 77% at most): gpt-oss 120B picked it for 62% (56% of its picks the
  person's; 29 s a claim), Qwen3.5 9B 60% (48%; 1 s), Qwen3.5 35B 58% (50%; 3 s), Gemma 4 12B 58% (46%; 2 s), Gemma 4
  26B 57% (54%; 2.4 s), Qwen3 8B 53% (42%), and the live Qwen3 30B-A3B 52% (52%; 4.6 s). Differences of a few points
  are within what 60 claims can tell apart; every model beat the live method's 37%. Qwen3.5 under Ollama returned an
  empty list whenever the schema asked for a list of fixed strings, so its answers are asked for as numbers.
- **A claim may have no motif.** Until now a claim whose last motif a person removed was filed again next run, and the
  model was asked for one to three motifs per claim, so claims that only report an event were forced into one. Now the
  model may give none ("a claim that only reports an event or states a fact, with no story told around it, gets
  none"), a claim whose last motif a person removes keeps none and isn't filed again, and on the motif board a person
  can mark a claim "no motif: not a story", which takes it out of every motif for good.
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
