# Claim praxis (DRAFT)

**A draft for the person to edit, written by Claude on Oct 12, 2026. Nothing here is in force.** The prompts, the
wording rules in `app/claim_wording.py` and the index are unchanged; where this draft says a prompt should change, it
is a proposal. Companion to `docs/motif-praxis.md` (whose rules 8-12 are about claims).

The decision it writes out (the person, Oct 12): "Claims: one side's assertion in that side's voice. A dispute is a
telling with a stasis line and side-claims (often a counter pair), never a sentence about the dispute ("the argument
revolves around x, y and z" is a stasis, not a claim; the eight-motif Green Party claim is the cautionary case)."

The casebook is the person's wording corrections (✎) as they stand in the index on Oct 12: 111 entries in
`index['corrections']`, less 18 that are same-claim folds and 10 that are links in a chain of the person's own
rewordings (a typo fixed, a wording changed twice), leaves **83 corrections**. (The person counts 77; leaving out the
five name spellings that never reached the curation log and one capital letter gives 77, which may be the
difference.) 32 were typed by the person, 43 drafted by Claude in a session and approved there (8 on Oct 5, 35 on Oct
9-12), and 8 aren't in the log. Each correction's source is taken from the claim's record in the index.

## What a claim is, from any source

1. **One side's assertion.** Something a teller says is true: what happened, why, what someone is like, what will
   happen, what ought to be. One side's, never a summary of several sides.
2. **In that side's voice.** Word it as the teller would say it, at their strength, with their "because" and their
   charge. No frame around it: not "posts claim", "the voter believes", "a video shows", "critics say". Who said it
   and which side they're on go on the claim's record (source, side, quote), not in its words.
3. **A dispute is a telling, not a claim.** When tellers disagree, the telling has a **stasis line** (the point at
   issue, worded as the question the sides meet on) and **side-claims** (each side's assertion in its own voice),
   often a counter pair. The stasis line is not filed under motifs; the side-claims are, each on its own. Never one
   sentence about the dispute.
4. **Strip what isn't the telling:** a fact-checker's verdict, the reporting frame, the medium it travelled in, dates,
   places and numbers the claim doesn't turn on.
5. **Add nothing:** no motive, threat or tone the tellers don't voice.
6. **Allegations against real people stay allegations** ("accused", "is said to"); lesser-known people by their role.
   This is the one hedge that stays in a claim's words, and only where the claim would otherwise state a crime or
   misconduct as fact.
7. **Short and plain:** one sentence, usually under 20 words. A claim that needs more is usually two side-claims or a
   claim plus its stasis.

**Stasis**, from classical rhetoric (Hermagoras; Cicero, *De inventione*): the point where two sides' assertions meet,
the question a dispute is about. The old four kinds fit the corpus's disputes well: *fact* (did it happen: "Did the
Cornell accuser consent?"), *definition* (what is it: "Is Israel's war in Gaza a genocide?", "Is Zionism racism?",
"Is it fair to call them Nazis?"), *quality* (is it justified: "Should the execution be livestreamed?") and
*procedure* (who should decide, by what means: "Should Democrats impeach Trump and Vance?"). Most of the casebook's
disputes are definition stases.

**The cautionary case.** The person's correction of Oct 7 turned a one-sided posts claim into "Arguments over the Green
Party's 'Zionism is racism' motion: whether Zionism is inherently racist, and whether anti-Zionism is antisemitism."
It is now filed in eight motifs (Antisemitic left, Weaponized antisemitism, Words mean things, By their fruits,
Political infighting, Institutions sell their soul, Own goal, Chapter and verse): every motif either side tells
lands on one claim, so the motif can't say which side told it, and the filing models learn that one sentence fits
eight shapes. Under this praxis it would be a stasis line ("Is Zionism racism? (the Green Party's motion)") with a
side-claim for each side the posts carry, each filed only under the motifs its own tellers tell. The side-claims'
words should come from the posts, not from this draft.

## By source

### Posts (folklore groups; `app/narratives.py` PROMPT)

- **What counts:** the narrative most of a group's posts retell. A claim in only one or two posts isn't the group's.
  A group that only shares a topic gets no claim.
- **Voice:** the posters', at their strength. Not "Posters say", "Posters mock", "Posters compare" (eight recent
  corrections added that frame; see the casebook's open points).
- **Stripped:** the reporting frame, and any reading of tone the posts don't voice ("JD Vance is portrayed as
  ignorant... often in a humorous or mocking tone" became what Vance said and what the posters made of it).
- **Disputes:** the commonest source of them (9 of the 13 dispute corrections). A group whose posts argue gets a
  stasis line and two or three side-claims, never "Posters argue over X: whether a, whether b, whether c".
- **How many:** one claim per group, or for a dispute one stasis line and at most three side-claims.
- **Support:** each side-claim needs posts of the group that tell it; two or more, as the repetition bar asks. Today
  the ABOUT check asks only whether half the posts are about the claim, "telling it ... or arguing over it" alike, so
  a sentence about a dispute passes it.
- **The prompt today:** asks for one "narrative" in one plain sentence and gets RULES, SHORT and eight examples. It has
  no place for a stasis line or side-claims, and RULES tells it to word a disagreement as "Arguments over
  whether...". The eight examples it is shown today (`claim_wording.examples('posts')`) include "Posters fault
  Britain's Green Party from several sides: ..." and "Posters compare X and Bluesky: ...", the shape the decision
  rules out, and seven of the eight open with "Posters say/fault/mock/compare" or "Police say".

### Fact-checks (`app/analysis/factchecks.py` LABEL_PROMPT)

- **What counts:** the claim the piece checks, as the people spreading it state it. The tellers are the posters,
  politicians or ads the piece quotes; the checker is not a teller.
- **Voice:** the teller's. Read the posts the piece quotes, not only its "What was claimed" line or headline: those
  are the checker's own normalisation, and they are where "A video shows X" comes from (see Caught on camera below).
- **Stripped:** the verdict (9 corrections, all fact-checks; the most uniform kind in the casebook), the checker's
  question form ("Does a real video show...?" gave four claims beginning "A real video shows"), and the medium.
- **Disputes:** rare. A piece checks one side's assertion; the checker's correction is never its counter-claim. When
  the checked claim is itself one side answering another (an ad attacking a candidate), the claim is the ad's.
- **How many:** one per piece; "" if it checks no single claim. A compilation of several false clips is one claim
  only if the posters tell them as one story.
- **Support:** where the piece quotes a post, the claim should be something that post says.
- **The prompt today:** says "never the fact-checker's correction or verdict", which matches. But it also asks for
  "who says it (a politician, posts on social media, a viral video) and in what setting", which invites "A viral
  video on social media claims to show..." and contradicts SHORT, appended to the same prompt ("not who reports it
  or where it circulates"). Its examples today include two of the same Rapinoe correction (a chain link) and a
  same-claim fold ("Photos show a gold statue..."), and the Hinson correction, which keeps the verdict ("she in fact
  voted for their release").

### Shows (`app/analysis/show_claims.py` PROMPT)

- **What counts:** what a speaker asserts about politics and public life; not what they quote only to knock down,
  not wishes or plans, not ads.
- **Voice:** the speaker's, at their strength ("The media provides untruthful information to the public" became "The
  mainstream media is lying to and about the American people"). Who spoke goes in `speaker` and the quote.
- **Stripped:** "the host says", "the speaker"; a host's paraphrase when the claim is a played clip's.
- **Disputes:** hosts arguing with guests, or a show setting two clips against each other. Stasis line from the
  exchange; one side-claim per speaker, each with its own quote. "Each side says the federal government is being
  turned on its enemies: one, that...; the other, that..." becomes "Is the federal government being turned on its
  enemies?" with the two sides' claims, each quoted.
- **How many:** up to five per part, as now; a dispute's side-claims count toward the five.
- **Support:** the quote (at most 25 words, from the transcript) must carry the claim's central part, and the speaker
  must be right; the support check (`focus_group.supported`) already runs on shows' claims.
- **The prompt today:** says the speaker's own claim, without saying who says it, and "not ones they quote only to
  knock down", which matches. Its eight examples average 27 words and include "Whether Israel's actions in Gaza are a
  genocide is argued: Cruz says...; Hasan says..." and "Each side says...": one sentence carrying both sides.

### Focus Group (`app/analysis/focus_group.py` PROMPT)

- **What counts:** what the voters believe, have heard or say someone is like; not the hosts' or guests' analysis
  (a played clip of David French is French's, not a voter's), not wishes or plans.
- **Voice:** the voter's. A claim that is personal testimony may need the first person ("AI fact-checks information
  from social media for me"). A stated concern is worded as the belief behind it ("APEC is a significant issue
  because of their funding history" became "political contributions should be funded by U.S. individuals or
  organizations, not foreign entities").
- **Stripped:** "the voter believes", "voters believe", the side label (it goes in `side`).
- **Disputes:** voters disagreeing in one group. Stasis line, one side-claim per voter or camp, each with its quote.
- **How many:** none to three a part, as now.
- **Support:** the quote must be the voter's words and say the claim, not a neighbouring one ("Politicians cheat on
  their spouses but still get elected" over a voter saying politicians tell you what you want to hear). Names are
  where transcripts fail most: all nine name fixes in the casebook are Focus Group claims (APEC and APAC for AIPAC,
  Wattley for Whatley, Shapiro for Josh Shapiro).
- **The prompt today:** says the teller's own terms, without saying who says it, "who said it goes in quote and side",
  which matches. Its eight examples contradict it: "A Republican voter says...", "A swing voter says...", "A Black
  voter says...", "A voter finds...".

## Where the prompts already say it

| rule | posts | fact-checks | shows | Focus Group |
|---|---|---|---|---|
| teller's voice, no frame | SHORT | SHORT, but "who says it ... a viral video" | yes | yes |
| no verdict | RULES | yes | (n/a) | (n/a) |
| stasis line plus side-claims | no; RULES says "Arguments over whether..." | no | no | no |
| keep the because, charge, strength | RULES | RULES | RULES | RULES |
| add nothing | RULES | RULES | RULES | RULES |
| allegations hedged, people by role | RULES | RULES | RULES | RULES |
| side label off the claim | no (posts carry `side`) | no | yes (`speaker`) | yes (`side`) |
| how many | one | one | up to five | none to three |
| what supports it | ABOUT check, half the posts | nothing | quote + support check | quote found + support check |
| short | SHORT | SHORT | SHORT | SHORT |

And everywhere: the same-source examples now teach the opposite of three rules (sentences about disputes, "Posters
say"/"A swing voter says" frames, length; they average 19-27 words against SHORT's 20). Cordelia's results will
measure the examples as they are.

**Proposals, for the person to decide:** (1) replace RULES' disagreement line with the stasis-and-side-claims rule,
and add a place for a dispute in each source's answer (a stasis line and a list of side-claims); (2) keep out of the
examples the corrections this decision overturns, same-claim folds and chain links; (3) in LABEL_PROMPT, drop "a
viral video" from "who says it" and point the model at the posts the piece quotes; (4) replace RULES' and SHORT's
"A video shows..." examples (see Caught on camera); (5) give side-claims the same support test as claims: posts for
posts, a quote for shows and the Focus Group.

## The casebook: 83 corrections by kind of fix

| kind of fix | all | posts | fact-checks | shows | Focus Group |
|---|---|---|---|---|---|
| a dispute reworded | 13 | 9 | | 4 | |
| kept the part that makes it a story | 12 | 3 | 3 | 1 | 5 |
| stripped a verdict | 9 | | 9 | | |
| fixed what the source says (misread, inverted, invented) | 9 | 3 | | 1 | 5 |
| names spelled | 9 | | | | 9 |
| who says it | 7 | 2 | | 1 | 4 |
| the teller's strength | 6 | 2 | 1 | 3 | |
| allegations hedged, people by role | 6 | 3 | | 3 | |
| exact facts | 5 | | 3 | 2 | |
| naming the subject | 3 | 2 | | 1 | |
| shortened | 1 | | | | 1 |
| a concern as the belief behind it | 1 | | | | 1 |
| other (a capital letter; a verdict kept) | 2 | | 2 | | |
| **all** | **83** | **24** | **18** | **16** | **25** |

Each correction is counted once, by its main fix; many do two things. **Length:** the person's wordings are longer
than the model's, not shorter: posts 18.8 words to 24.2, shows 12.6 to 25.9, Focus Group 12.0 to 13.8, fact-checks
12.8 to 14.7. Only one correction does nothing but cut (the Waterford police claim). The length comes from three kinds:
keeping the story, rewording disputes, and adding who says it; this praxis would move the dispute length into
side-claims and drop the frames.

### Stripped a verdict (9, all fact-checks)

The clearest kind, and the one the decision's "that side's voice" generalises.

- "The video shows Muslim women queuing for a clothing sale, not free childcare" → "A video shows Muslim women
  queuing for free childcare."
- "Democratic ads misleadingly connect Susan Collins to Jeffrey Epstein." → "Sen. Susan Collins covered up Epstein
  files and got $3 million from Epstein's business partner"
- "Fake videos distorted real protests in France, and Elon Musk was falsely quoted..." → "Videos claim French student
  protests have escalated into revolution: protesters storming the stock exchange, police and firefighters joining
  them, ..."
- Exceptions to decide: "Ashley Hinson voted for Epstein files' release." → "A Democratic ad says Ashley Hinson's top
  donors appear in the Epstein files and that she voted against releasing the files; she in fact voted for their
  release." (the verdict kept as a tail); and "A video showing BBC News linking an Indian passenger to the Flydubai
  attack is a deepfake" → "A deepfake video showing BBC News linking..." (the verdict kept as an adjective).

Six of the nine became "A video shows X" (as did the Dublin claim): the verdict went, the checker's frame stayed. See Caught on camera.

### Kept the part that makes it a story (12)

- "Megan Rapinoe called for Jason Kelce's firing." → "...after he used the Washington Commanders' former name
  "Redskins" because it is racist." (the because)
- "The President of the United States is a liar." → "...a liar and Putin's puppet." (the charge)
- "Megyn Kelly is a vile, heartless, and soulless person who deserves no platform..." → "...and yet faces no
  consequences." (the consequence)
- "Ken Paxton is better off out of the state" → "Some Republicans who dislike Ken Paxton are said to want him in the
  Senate just to get him out of Texas." (the reason)
- "Communism is currently losing influence in South America." → "Communism is on the run in South America now that
  USAID money no longer props up the left." (the because, and the strength)

### Fixed what the source says (9)

- "James Fishback is a talker who doesn't use big words and is untrustworthy" → "...who uses big words..." (inverted)
- "Politicians cheat on their spouses but still get elected." → "Politicians always tell voters what they want to
  hear." (the wrong claim for the quote)
- "Donald Trump is angry at Fox News for not covering his rallies adequately and is threatening to retaliate." →
  "Trump rages at Fox News for not covering his rallies, boasting of packed houses and saying he's stopped watching."
  (an invented threat; RULES' "add nothing" example)
- "A political figure is threatening to bomb an American city as a way to declare an emergency and stop elections."
  → "A leader remarked that American cities could be bombed, and critics expect him to dismiss it as a joke."
  (an invented motive)

### A dispute reworded (13: posts 9, shows 4)

The person's own four (Oct 7-8) used "Arguments over whether..." or "Democrats debate whether...; many argue...";
the nine drafted by Claude (Oct 9-12) carried the sides in one long sentence. **This decision overturns most of
them.**

- Sentence about the dispute (the cautionary shape): "Arguments over the Green Party's 'Zionism is racism' motion:
  whether Zionism is inherently racist, and whether anti-Zionism is antisemitism." (eight motifs); "Posters argue over
  the Greens: whether the media ignores their climate focus, whether Green votes prop up the government, and whether
  Greens did entryism into Labour in 2015."; "Posters fault Britain's Green Party from several sides: ..."; "Posters
  compare X and Bluesky: ..."
- Both sides in one sentence: "Whether Israel's actions in Gaza are a genocide is argued: Cruz says it's Hamas that
  advocates genocide; Hasan says 'when it's a genocide, it's a genocide.'"; "Homeland Security Secretary Mullin says
  livestreaming Nidal Hasan's execution would help restore American values; critics call it barbaric..." These are
  nearest to the new shape: split at the semicolon, add the stasis line, and they are two side-claims.
- One claim, two sides (praxis rule 12): "Both sides of Brazil's election say they're being censored: the right
  says...; the left says..."; "Each side says the federal government is being turned on its enemies: ..." The decision
  seems to supersede rule 12's "reword the claim to carry both": a stasis line ("Who is censoring whom in Brazil's
  election?") and two side-claims, both filed under the same censorship motif. For the person to say.
- The model's own sentence about a debate, which the person replaced with a side's claim: "Both older people relying
  on Social Security and younger people paying into it have valid perspectives in the debate." → "Most older
  Americans want Social Security protected even if younger workers pay higher taxes for it; ..." This is the
  decision's point made by a correction: the model's sentence was a stasis, not a claim.

### Who says it (7) and side labels

- Rightly corrected: "The voter believes that Donald Trump has changed the culture of the evangelical church..." →
  "David French argues that..." (a played clip, not a voter: the claim belongs to French's telling).
- Frames added: "Democrats target people based on appearance rather than engaging in genuine dialogue." → "A Black
  voter says Democrats target people who look like her, assuming they're her friends, instead of making their case.";
  "Trump's economic plan initially raised prices due to tariffs" → "A Republican voter says kitchen-table issues
  decide their vote, and Trump's tariffs first pushed prices up."; and "Posters say..." on three posts claims. These
  name the side in the claim (rule 10) and put a frame round the voice. In the voter's voice: "Democrats target people
  who look like me, assuming we're their friends, instead of making their case." **Open point:** keep the frame where
  who says it is part of the meaning (the voter's own identity, "people who look like her"), or always move it to the
  record?

### The teller's strength (6)

- "The media has failed to maintain a professional distance from the Democratic Party." → "The press has become an
  arm of the Democratic Party, rooting for the people it is supposed to cover."
- "The accuser's changing story suggests her credibility is questionable." → "The Cornell accuser's story is said to
  keep changing, enough to doubt everything she says, and one of the accused now says she was the one who assaulted
  him."
- One went the other way: "Paxton made inflammatory comments about the Uvalde shooting." → "...insensitive comments..."
  (the tellers' word, not a stronger one).

### Allegations hedged, people by role (6)

- "Jacob Geller is a rapist who has avoided accountability..." → "After a prominent YouTuber admitted to a past sexual
  assault, critics say he is dodging accountability and still profiting."
- "Cornell University is complicit in rape culture by allowing rapists to write essays..." → "Critics say Cornell let
  students accused of rape off with writing essays, and call it rape culture."
- "Jane Doe only concluded she was assaulted after she was disinvited from a party." → "The Cornell accuser is said
  to have decided she was assaulted only after she was disinvited from a Halloween party..."

"Critics say" here is the allegation hedge (praxis rule 9), not a voice frame; this draft keeps it for allegations
against real people only.

### Names, facts, subject, concern (19)

- Names (9, all Focus Group): "APEC"/"APAC" → "AIPAC" (five); "Wattley" → "Whatley" (three); "Shapiro" → "Josh
  Shapiro".
- Exact facts (5): "Trump renamed the Kennedy Center to the 'Department of War'." → "Trump renamed the Kennedy
  Center and the Department of Defense and other things"; "Trump's political consultants provided election advice to
  a Russia-aligned government in Bosnia." → "Trump-linked consultants were paid through a D.C. law firm to advise
  Republika Srpska's pro-Russian government on elections."
- Naming the subject (3): "The event will be made available as a Pay-Per-View." → "Posters predict the livestreamed
  military execution will be sold as pay-per-view, since 'they monetize everything.'"; "Trump cannot fire her
  because..." → "...won't fire Ambassador Kimberly Guilfoyle...". A claim has to stand alone on a chip.
- A concern as the belief behind it (1): the AIPAC funding claim above.

## Outside anchor: CheckThat! 2025 Task 2, claim normalization

CLEF 2025's CheckThat! lab, Task 2 (overview: Sundriyal and Nakov, CEUR-WS Vol-4038, paper 52,
https://ceur-ws.org/Vol-4038/paper_52.pdf), asked systems to rewrite noisy social-media posts "into clear, concise,
and factual statements, the way that human fact-checkers formulate the claims they are checking". About 28,000
post-claim pairs in 20 languages (13 with training data, 7 zero-shot), built from CLAN (Sundriyal, Chakraborty and
Nakov, EMNLP Findings 2023), MultiClaim and two other sets; the gold claim is the fact-checker's own short summary of
the claim checked; systems are scored by METEOR overlap with it. 18 teams; the leaders fine-tuned Qwen models with LoRA, prompted LLMs
with the most similar training pairs retrieved as examples (as Cordelia shows the person's corrections), or reused
an existing normalization when a similar post had one; the top team (dfkinit2b) chose among five methods' outputs
the one nearest their centroid.

What it shares with this praxis: one claim per post, stripped of noise, short. Where it differs, and why we keep our
own gold:

- **Its gold is the checker's wording**, which is what this praxis strips (Caught on camera below is the result of
  taking it as ours).
- **It normalises the teller's framing away.** Its French example turns a post about a baby born in the Bafoussam
  landslide, told as one of God's "wonders and miracles", into "Born during the landslide in Bafoussam."; its German
  example drops "the stupidest voters". For a folklorist the miracle is the telling; here it is noise. Its English
  example does keep an argument's "so" ("Vaccines for HIV, cold, and cancer should deter you from getting the
  Covid-19 vaccine"), as RULES does.
- **It has no disputes.** A post has one claim; there is no stasis or counter-claim.
- One source set kept only posts with text, dropping "only image or video content": the field also treats the
  medium as something other than the claim.

So it is an anchor for the task's shape (post in, one short checkable sentence out, judged against a person's
wording, examples retrieved by likeness) and for the measure (an overlap score against the curator's wording, which
the Brothers Grimm did with embeddings), not for what the sentence should keep.

## Caught on camera: whose format is "a video shows"?

**The motif:** M173 Caught on camera (Arguments; note: "A video or photo is offered as direct proof of what is
really happening, often something alarming that the news won't show."). It holds 27 claims, all from fact-checks
(Full Fact, Lead Stories, PolitiFact, Snopes), Sept 29 to Oct 12; `told` counts 20 events. 26 of the 27 are
worded as what a video, photo or image shows ("A video shows", "A real video shows", "A viral video showed", "A
photo shows"); the 27th is about Steinway pianos.

**Method:** `claim_detail` for each of the 27 (the fact-check's text as read by the hourly run), then the posts each
piece quotes. Ten cases where the piece quotes the tellers:

| claim (as filed) | what the tellers said | verdict |
|---|---|---|
| A viral video showed protests in Iran in the fall of 2026 | X post: "Thousands of Iranians are on the streets"; "Why is the Legacy Media not reporting this?" | the event, plus media silence; the video is the vehicle. Nearest of the ten to the motif's note, but nobody points at the footage |
| A video shows the stabbed pilot aboard the FlyDubai plane during the hijack attempt | X post: "A passenger reportedly captured dramatic footage from the window of the Flydubai aircraft" | the footage is named, as news, not as proof against doubt |
| A video shows a large group of Muslims chanting on the streets of Dublin in September 2026 | Caption: "this just happened yesterday in the Irish Capital - no Police to be seen"; "No these are not Irish people."; John Cleese: "The Religion of Peace" | the event and a charge; checker's format |
| A video shows Muslim women queuing for free childcare | Caption: "a queue of all Muslim Women waiting to enroll their children for FREE Daycare" | the event (free welfare for Muslims); checker's format |
| A video shows Sen. Katie Britt saying she thinks 'America deserved 9/11' | X post: "Senator Katie Britt booed at rally after stating that she thinks 'America deserved 9/11'" | what she said; checker's format |
| A photo shows a signal jammer installed by police in Dover... | X post: "Kent police have put signal blockers near cruise terminal in Dover" | the event (police block livestreams); checker's format |
| A video shows young men dressed in black dancing with guns at student protests in France | Benny Johnson: "These are the 'French Student protestors'."; "Do any of them even look French?" | **the teller's own move**: look at them, here is what they really are |
| A real video shows a large ship completely engulfed by a massive wave... | X post: "how they managed to cross this ocean with medieval technology" | a joke; no claim about the video; "real" is from the checker's question |
| A video shows Flávio Bolsonaro telling a Masonic lodge he would give Brazil to 'Greater Israel' and Satan | X post: "Flavio Bolsonaro swears before the Grand Masonic Lodge of Brazil"; "hand over the country to 'Greater Israel' and his god, Satan" | the event; checker's format |
| A video shows a funeral procession in Gaza scattering when air raid sirens sound... | Facebook post: "including, apparently, the 'dead' man on the stretcher" | **the teller's own move**: the clip as proof the dead are faked |

Across all 27: in 2 the teller offers the footage as proof (France, Gaza), with Iran a borderline third; in 5 the
teller names the footage itself but as news or a hint (the FlyDubai cockpit and "leaked video", the FlyDubai
"partying" clip, "New video footage of the moment" at Riyadh, "Natalie putting on gloves. Because... why
exactly??"); in 13 the teller tells the event and the video is only how it travelled (US strikes on Iran, Sheffield,
Dublin, the Amsterdam queue, the crying soldier, Albanese twice, Cornell, Britt, Dover, Bolsonaro, the Israel oil
strike, Bill Gates); in 5 the post is no claim about an event (the bus-driver story, the gymnasts, Noah's Ark, the
ship, "UK peoples Stand with Palestine"); and one isn't a video at all ("The Kennedy Center is selling its Steinway
pianos").

**Where the format comes from.** Not from the tellers. (1) The checkers write it: Full Fact's "What was claimed: A
video shows...", Lead Stories' "Does a video show X? No, that's not true" (four claims kept its "a real video"). (2)
LABEL_PROMPT lists "a viral video" among "who says it". The labeller writes it unprompted too: the Dublin
claim's first wording, before any correction, was already "A video shows a large group of Muslims chanting in
Dublin". (3) On Oct 5 corrections drafted by the 30B model, edited by Claude and approved by the person turned six
checkers' verdicts and the person's own verdict wording of the Dublin claim into "A video shows X": the right fix for
the verdict, which kept the checker's frame. (4) Since Oct 12 RULES' first example ("A video shows soldiers
looting a church") and SHORT's ("A video shows a crowd storming a stadium") put the format in every claim prompt.

**What it implies.** Caught on camera is a real shape, and the tellers' own (praxis: "a teller offering proof is an
Argument ... 'here's the video'"), but the index holds it on about three tellings. The other 24 claims are there
because their words begin "A video shows", which is the checker's format, so the filing model matches the frame
rather than the telling. Rule 6 already says the mechanics (fakes, old footage, clipped video) aren't motifs; the
medium isn't either.

**Proposed, for the person to decide:**

1. Reword the "a video shows" claims to what the tellers assert, from the posts the pieces quote ("Thousands of
   Iranians are on the streets to take back their country, and the media won't report it"; "Muslim women line up to
   enroll their children in free state daycare"; "Senator Katie Britt said America deserved 9/11 and was booed").
   Keep the footage in the words only where the teller makes it the point ("These are the French student
   protesters: do any of them look French?").
2. Re-file after rewording: keep in Caught on camera only claims whose tellers offer the footage as proof (France,
   Gaza; Iran and the Harp photo to judge), and give the motif a 🚫 line: "not every viral video: the teller has to
   offer the footage as proof".
3. Keep the medium (video, photo, AI clip) on the claim's record as data for the flow layer, not in its words.
4. Change the prompts' "A video shows..." examples and LABEL_PROMPT's "a viral video" (proposals 3 and 4 above).

The five non-claims (a joke, a marvel, a slogan, a narrated tale) are a separate question: Perennials or no motif,
under rule 11.
