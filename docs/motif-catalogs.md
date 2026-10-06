# Prior catalogs: how the BND Motif Index compares, and how to map it

Folklorists, political scientists and computational linguists have built catalogs of the stories, frames, claims and
tricks people use. Our motif index is another one, so it should be read against them: what it shares, what it adds,
and where its motifs line up with theirs. This note covers both, and plans the mapping for the ~Oct 12 motif review.
Started Oct 6, 2026 (from a side conversation; see also `docs/motif-tools-research.md` and issue #145).

## The catalogs

| Catalog | Unit | Built from | How it's organized | What it shares with ours |
|---|---|---|---|---|
| **Thompson, *Motif-Index of Folk-Literature*** (1932–36; rev. 1955–58) | a motif: the smallest recurring element of a tale (an actor, object or incident) | folktales, myths, romances and fables worldwide, through archives and published collections | chapters A–Z, decimal numbers that place each motif in a hierarchy (K = deceptions; K2100 false accusations), "cf." cross-references | the name and idea of a motif; a hierarchy of kinds; cross-references like our "related". Chapter K (deceptions), P (society), Q (rewards and punishments), S (unnatural cruelty) and W (traits of character) fit political talk best (#145) |
| **ATU tale-type index** (Uther 2004, after Aarne 1910 and Thompson 1928/1961) | a tale type: a whole plot (510A Cinderella, 1620 The Emperor's New Clothes) | European-centered folktale collections | about 2,000 numbered types in ranges (animal tales, tales of magic, jokes) | little: our #145 prototype found whole tale types the wrong grain for news (the Braves' win came out as Cinderella); joke types might suit satire |
| **Brunvand's type-index of urban legends** (*The Baby Train*, 1993; expanded in *Encyclopedia of Urban Legends*, 2001/2012) | a legend type: a plot kernel told as true | contemporary legends Brunvand collected and published | by content: automobiles, animals, horror, accidents, sex and scandal, crime, business and professional, government, celebrities, academic | the closest grain to ours: stories told as true, in modern life. Government, crime and contamination legends overlap political rumor |
| **Barkun's conspiracy typology** (*A Culture of Conspiracy*, 2003; 2nd ed. 2013) | a conspiracy belief, by scope | American conspiracy subcultures | event conspiracies, systemic conspiracies, superconspiracies; and three principles: nothing happens by accident, nothing is as it seems, everything is connected | a **facet**, not a catalog: any conspiracy motif of ours can be tagged with its scope |
| **Tangherlini's narrative frameworks** (Tangherlini et al., *PLOS ONE* 2020; Shahsavari et al. 2020 on COVID-19) | a narrative framework: actants and the relations between them, as a network | posts on Reddit, 4chan and news comment threads, read by machine | one graph per conspiracy theory, built from subnarratives; a theory is fragile where it hangs on thin links between subnarratives | the method: bottom-up from what people post, by machine. They model one conspiracy deeply; we catalog recurring claim shapes across every topic |
| **Narrative Policy Framework** (Jones & McBeth 2010; Shanahan, Jones & McBeth 2018) | a policy narrative's form | policy documents, testimony, news, interviews | setting, characters (hero, villain, victim, and later beneficiary, ally, opponent), plot, moral; strategies such as widening or narrowing the conflict | another **facet**: our narrative labels already name villain, victim and hero (#142) |
| **Media Frames Corpus** (Card et al., ACL 2015) on the Policy Frames Codebook (Boydstun et al. 2014) | a frame dimension of an article or passage | 35,701 US newspaper articles 1990–2012 on immigration, tobacco, same-sex marriage, later gun control, the death penalty and climate | 15 generic frames: economic; capacity and resources; morality; fairness and equality; legality and constitutionality; policy prescription; crime and punishment; security and defense; health and safety; quality of life; cultural identity; public opinion; political; external regulation and reputation; other | a coarse **facet**: every motif sits in one or two of these. Theirs says how an issue is framed; ours says what story is told |
| **CARDS** (Coan, Boussalis, Cook & Nanko, *Scientific Reports* 2021) | a contrarian claim about climate change | conservative think-tank and contrarian blog writing, 1998–2020, classified by a trained model | five super-claims (it isn't happening; humans aren't causing it; the impacts aren't bad; the solutions won't work; climate science and the movement are unreliable), each with sub-claims, three levels deep | the same grain (claims) and the same shape (a hierarchy of claims), for one domain, built top-down by experts. A model for what a mature claim catalog looks like |
| **SemEval propaganda and narrative tasks**: 2020 Task 11 (Da San Martino et al.), 2023 Task 3 and 2025 Task 10 (Piskorski et al.) | 2020/2023: a persuasion technique in a passage; 2025: a narrative and subnarrative of an article, and each named entity's role | news articles, hand-annotated, in up to nine languages | 2020: 14 propaganda techniques; 2023: genre, 14 frames (the Media Frames set) and 23 persuasion techniques in 6 groups; 2025: a two-level taxonomy of narratives for two domains (the war in Ukraine, climate change), and entity roles (protagonist, antagonist, innocent, with finer roles) | techniques are **how** something is said (a facet); the 2025 narratives are **what** is claimed, the closest thing to our motifs in NLP, top-down for two domains |

Also worth comparing later: EUvsDisinfo's database of pro-Kremlin disinformation cases tagged by narrative, and the
DISARM framework (formerly AMITT), which catalogs disinformation tactics and techniques rather than stories.

## What's likely distinctive about ours

To be checked against the literature, but likely:

1. **Bottom-up from live US political talk.** The catalogs above were built from folktale archives, expert reading of
   one domain, or hand annotation of news. Ours grows each day from what people say: retold posts on Bluesky and
   Mastodon, voters in focus groups, and rumors fact-checkers took up, across every topic at once.
2. **Each motif is tied to its spread.** A motif's claims come with where they came from and how they traveled: the
   stories and outlets they ride on, which side tells them, how many people retold them, and the source kind (online,
   focus group, fact-check). The catalogs above record a story's type, not its circulation.
3. **Tracked over time.** First and last seen, narratives told again on later days (narrative threads), new claims
   since a person last looked, and a log of every curation decision (`curation_log.jsonl`), so how the catalog was
   built is itself on record.
4. Smaller points: a person and a local model build it together, every model step tested against the person's own
   decisions; and a claim may have no motif (no forcing).

Closest relatives: Tangherlini's work (bottom-up, social media, by machine) and SemEval 2025's narrative taxonomy
(claim-level, two levels). Neither is cross-topic and continuously growing.

## Mapping our motifs to the catalogs (for the ~Oct 12 review)

Plan: link each motif to the entries it matches in the catalogs, using the SKOS mapping properties, so the index can
be read alongside them and the motifs with no match stand out as candidates for something new.

1. **Export the index as SKOS.** Each motif a `skos:Concept` with `skos:prefLabel` (its name), `skos:scopeNote` (its
   note), `skos:broader` (its kinds' parents), `skos:related`; its claims and spread in our own properties.
   *Done Oct 6:* `app/analysis/motif_export.py` (the workbench's 📦 export, or `scripts/export_motifs.py ttl`), at the
   motifs' addresses on the site (`bnd:` = `https://bignews.day/motifs.html#`), claims as `skos:example`, genre as
   `dct:type`, groups as `skos:Collection`s; verified motifs only unless `--all`. Spread isn't in it yet.
2. **Load the catalogs we can use.** Machine-readable: Thompson's index (a CSV transcription exists, e.g.
   KatjaMellmann/TMI_as_CSV on GitHub), the 15 Media Frames, CARDS's taxonomy (its replication repository), the
   SemEval 2025 narrative taxonomy (in the task paper and data). By hand, numbers and names only (the books are under
   copyright): ATU types and Brunvand's legend types for the motifs that look like them. Barkun's scope, the NPF roles,
   the frames and the SemEval techniques are facets: tag, don't match.
3. **Find candidates and judge them** the way we file claims: the closest entries by embedding (motif name, note and a
   few claims against each entry's text), then the judge (gemma4:26b) side by side: same story shape, broader,
   narrower, related, or none.
4. **A person decides** in the motif workbench (a "prior catalogs" panel on each motif): accept as
   `skos:closeMatch` (or `exactMatch`, `broadMatch`, `narrowMatch`, `relatedMatch`), or reject.
5. **Read the result:** the share of motifs matched in each catalog; which catalogs cover which kinds of motif; and
   the **unmatched motifs**, by side and source. Those are the candidates for what's new: stories of current US
   politics that the older catalogs don't have.
6. Later: publish the links on the public motifs page, and the SKOS file for other researchers (#146).

## Sources

- Thompson, S. *Motif-Index of Folk-Literature*, rev. ed., 6 vols., Indiana University Press, 1955–58. Searchable via
  MOMFER (<https://momfer.meertens.knaw.nl/>).
- Uther, H.-J. *The Types of International Folktales* (FF Communications 284–286), 2004.
- Brunvand, J. H. *The Baby Train and Other Lusty Urban Legends*, 1993 (with "A Type-Index of Urban Legends");
  *Encyclopedia of Urban Legends*, 2001, updated 2012.
- Barkun, M. *A Culture of Conspiracy: Apocalyptic Visions in Contemporary America*, 2003; 2nd ed. 2013.
- Tangherlini, T. R., Shahsavari, S., Shahbazi, B., Ebrahimzadeh, E. & Roychowdhury, V. "An automated pipeline for the
  discovery of conspiracy and conspiracy theory narrative frameworks", *PLOS ONE* 15(6), 2020.
- Jones, M. D. & McBeth, M. K. "A Narrative Policy Framework: Clear Enough to Be Wrong?", *Policy Studies Journal*
  38(2), 2010; Shanahan, E. A., Jones, M. D. & McBeth, M. K. "How to conduct a Narrative Policy Framework study",
  *The Social Science Journal* 55(3), 2018.
- Card, D., Boydstun, A. E., Gross, J. H., Resnik, P. & Smith, N. A. "The Media Frames Corpus: Annotations of Frames
  Across Issues", ACL 2015. <https://aclanthology.org/P15-2072/>
- Coan, T. G., Boussalis, C., Cook, J. & Nanko, M. O. "Computer-assisted classification of contrarian claims about
  climate change", *Scientific Reports* 11, 2021. Code: <https://github.com/traviscoan/cards>
- Da San Martino, G. et al. "SemEval-2020 Task 11: Detection of Propaganda Techniques in News Articles", 2020.
- Piskorski, J. et al. "SemEval-2023 Task 3: Detecting the Category, the Framing, and the Persuasion Techniques in
  Online News in a Multi-lingual Setup", 2023. <https://aclanthology.org/2023.semeval-1.317/>
- Piskorski, J. et al. "SemEval 2025 Task 10: Multilingual Characterization and Extraction of Narratives from Online
  News", 2025. <https://aclanthology.org/2025.semeval-1.331/>
- W3C. *SKOS Simple Knowledge Organization System Reference*, 2009 (mapping properties: §10).
