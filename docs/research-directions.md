# Modes of analysis over time

A running record of how bignews.day studies the news: the questions it asks and the lenses it uses, as they change.
The methods log (`docs/methods-log.md`) records each change to how things are measured; this records why, and the
directions of research behind them. Newest first. Add an entry whenever a new lens is taken up, changed or dropped.

## 2026-10-06: dissemination and its afterlife; reading the catalog against others

- **A story's travels as one flow.** "We're tracking the way an article disseminates, and then downstream of it what
  that information turns into as it morphs." Story pages follow each story from the front pages that broke it, out
  through wire copy, TV chyrons, radio newscasts and the shows, into what people retell online and what voters say,
  to what fact-checkers examine and the saga it joins. The trackers are stages of one flow, not separate features.
- **What television emphasizes.** TV news chyrons (CNN, Fox News, MSNOW, BBC News) matched to front-page stories: how
  long each channel spends on a story, beside how many front pages carry it.
- **The motif index against prior catalogs.** Compare our bottom-up catalog with Thompson, ATU, Brunvand, Barkun,
  Tangherlini, the Narrative Policy Framework, the Media Frames Corpus, CARDS and the SemEval taxonomies; map motifs to
  them as SKOS links at the ~Oct 12 review; the unmatched motifs are candidates for what's new
  (`docs/motif-catalogs.md`).
- **Will the index become a decision tree?** (A question, Oct 6.) As kinds deepen, filing a claim could become a walk
  down the tree, as Thompson's index is used: first the broad class, then the narrower one, a few choices at each
  step instead of the eight closest motifs at once. That would make the model's choices smaller and checkable, and the
  tree itself a test of the catalog: a level where claims can't be told apart is a level that isn't doing work.
  Genres (a second axis, added Oct 6) cut across it. To look at in the ~Oct 12 review.
- **Models chosen by the person's judgments.** Every local model is picked for its job by a test against a person's own
  decisions (motif filings, saga vetoes, label verdicts), not by benchmarks (`docs/models.md`). Method, not topic, but
  it shapes every result.

## 2026-10-05: a motif index, built bottom-up; the voters' own words

- **Folklore as the shape of political discourse.** The working thesis: folklore shapes political discourse, and the
  first step to understanding information warfare is understanding its folkloric shape.
- **Our own motif index replaces Thompson's chapters.** Thompson's index is built from folktales; political talk needed
  its own catalog. Claims (retold posts, fact-checked rumors, then voters' claims) are filed into motifs that grow
  bottom-up; a person curates. The plan: build the catalog for about a week, then judge what shape it took (~Oct 12);
  no codebook up front. A claim may have no motif.
- **Voters as a source of their own.** Focus Group transcripts read for the claims voters make, each with its quote
  and the voter's side, filed into the same motif index.
- **Narratives across days.** A narrative told on one day is looked for on earlier days (narrative threads):
  persistence, not just presence.
- **Radio running order** (#159): what the hourly NPR and ABC newscasts lead with, against the front pages.

## 2026-10-04: what people say unprompted; rumors and their shapes

- **Vernacular talk** (#153, #142): samples of Bluesky and Mastodon posts, grouped into paraphrases told by many
  people (folklore travels as variants) apart from copypasta; each big group labeled with its claim, genre and roles.
- **Rumors and fact-checks**: seven fact-checkers' feeds tied to stories, and each checked claim looked for in what
  people post (is it circulating?).
- **Satire** (#139): which stories become jokes. **Call-in shows**: raw talk from callers. **The Supreme Court**
  (#144): how the term's cases are covered by lean.
- **Mood redefined** as how the headline presents the news, not how good or bad the event is.

## 2026-10-03: the news as a corpus; folklore indices proposed

- **A digital humanities project** (#146): the site as a corpus of how the news is told, with research questions,
  not only a dashboard.
- **Folklore indices** (#145): read the news with Thompson's Motif-Index and ATU tale types. Prototypes showed tale
  types are the wrong grain for news; retelling a story as a nameless folktale was the interesting part.
- **Score provenance, outlet lean by AllSides, emotions ranked, stories and sagas**: the measuring instruments made
  explicit and versioned.

## 2026-10-02: the archive begins

The database starts this day: every outlet's front-page headlines each hour, with their mood, spice (loaded
wording), feelings, lean and the stories they form.

## 2024: Maudlin

Built by hand as Maudlin: per-outlet scrapers, a word cloud of the day's headlines and their sentiment by outlet. The
question then: how does the mood of the news differ across outlets?
