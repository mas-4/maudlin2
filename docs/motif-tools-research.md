# Tools for organizing motifs: what others have built

Our motif curation pages (the board, organizer, singles, map, notes, motif check and empty pages in `scripts/checker/`)
work on a known problem: a person and a model building a category system from a pile of short texts, bottom-up, and
keeping it tidy as it grows. Several fields have worked on it, under different names: qualitative coding, interactive
topic modeling, taxonomy building, entity resolution, card sorting, and folklore indexing itself. This is what they
found that we can use, with what each would mean here. Written Oct 6, 2026; the motif index review is due ~Oct 12.
For how our catalog compares with existing ones (Thompson, ATU, Brunvand, CARDS, SemEval…) and the plan to map our
motifs to them, see `docs/motif-catalogs.md`; for how the research directions have changed, `docs/research-directions.md`.

## What we have now

- The model files each claim against the 8 closest motifs side by side and names a new one only when none fits
  (`motif_index.py`); a claim may have no motif.
- A person merges, moves, splits off, says "kind of" (parent), "related", "not the same", "no motif", marks motifs done
  and writes scope notes; the model drafts notes for motifs with 3+ claims.
- The checker pages show the motifs as a board, singles with suggestions, a network map and tree, and a notes list.

## Software that organizes this shape of data

Our data has a particular shape: **short items** (claims) filed under **categories** (motifs), an item sometimes in
two categories; categories nested in a **hierarchy** (kinds) and joined by **relations** (related, not the same);
categories with **notes**; a **queue** of things to review; and a **pile of unfiled items**. Many tools manage this
shape. The question for us is how they lay it out and what you can do with a drag.

| Kind | Tools | How they lay it out | What a drag does |
|---|---|---|---|
| Qualitative analysis (QDA) | MAXQDA, ATLAS.ti, NVivo, Taguette (open source), Delve | A **code tree** beside the document; a code manager with each code's comment (memo) and counts | Drag a passage onto a code to code it; drag a code onto another to nest it (MAXQDA: up to 10 levels); merge codes; ATLAS.ti also draws codes as a **network** ([MAXQDA](https://www.maxqda.com/qualitative-coding-software), [ATLAS.ti](https://atlasti.com/research-hub/atlas-ti-alternative-to-other-programs)) |
| Research repositories | Dovetail, Condens | A **tag board**: tags as cards in named groups, each with its highlights | Drag a tag into a group to move it; **drop a tag on another to merge** ([Dovetail tags](https://docs.dovetail.com/help/projects/project-tags)) |
| Thesaurus and taxonomy managers | PoolParty, VocBench, TopBraid EDG, Protégé (ontologies) | **Concept tree** on the left, the selected concept's details on the right: labels, broader, narrower, related, notes | Drag a concept into another's Narrower section to move it, into Related to relate them, **onto its alternative labels to merge** ([PoolParty](https://help.poolparty.biz/en/user-guide-for-knowledge-engineers/basic-features/managing-your-thesauri/merging-concepts-by-drag-and-drop.html)) |
| Outliners | Workflowy, Dynalist, Logseq, Tana | **One tree** of everything; zoom into any node to work on just it | Drag to move or nest; Shift-drag makes a **mirror**, the same item live in two places ([Workflowy mirrors](https://blog.workflowy.com/mirrors-create-live-copies-of-any-bullet/)) |
| Whiteboards | Miro, FigJam, Heptabase, Obsidian Canvas | Cards on a canvas in **sections**; boards nested in boards; the same card on several boards | Drag cards between sections; Miro's AI clusters stickies by keyword into containers to start from ([Miro clustering](https://help.miro.com/hc/en-us/articles/4409706795410-Clustering), [Heptabase](https://wiki.heptabase.com/organize-knowledge-and-projects)) |
| Hypertext note tools | Tinderbox | The same notes as a **map, an outline or an attribute browser**; **agents** are saved searches that gather matching notes and keep them up to date ([Tinderbox](https://eastgate.com/Tinderbox/index.html)) | Drag in any view; arrangement on the map is meaning |
| Network maps | Kumu, Gephi, Cytoscape, InfraNodus | Elements and connections; **focus** on one element to see its neighborhood ([Kumu](https://docs.kumu.io/overview/kumus-architecture)) | Drag to arrange; draw a connection between two elements |
| Card sorting | OptimalSort, Maze, UXtweak | Cards to sort into groups; results as a **similarity matrix** and a dendrogram | Drag a card into a group, or make a new group by dropping on empty space |
| Annotation | Prodigy, Argilla, Label Studio | **One item at a time**, big, with the model's guess | Keys, not drags: accept, reject, skip, undo; the model picks what to ask next ([Prodigy](https://prodi.gy/docs/api-web-app)) |
| Boards | Trello, GitHub Projects | Columns of cards | Drag a card between columns |

What the best of them share, and what our pages lack:

1. **One window, three panes.** The categories as a tree or board on one side, the open category with its items in
   the middle, and the inbox (items to file, things to review) on the other side. Nothing needs a second page.
2. **Everything is draggable onto everything.** An item onto a category files it; a category onto a category merges,
   nests or relates it, chosen by where you drop or from a small menu at the drop; a category onto a group moves it.
   The drop target says what will happen before you let go.
3. **One search for everything**, items and categories alike, by name, number or words, with a keyboard shortcut.
4. **Focus**: open any category (or two side by side) without losing your place in the tree.
5. **A review queue with keys** for the quick yes/no work, ranked by what the model is least sure of.
6. **Undo** for every move, always visible.
7. **Saved views** (Tinderbox's agents): "singles", "no note yet", "not done", "unfiled" as filters on the same tree
   rather than separate pages.

## Techniques, by field

### 1. Qualitative coding: the codebook

Social scientists who code interviews (with NVivo, ATLAS.ti, MAXQDA, Dedoose) build a **codebook** as they go. The
standard entry, from MacQueen et al., "Codebook Development for Team-Based Qualitative Analysis" (*Cultural
Anthropology Methods*, 1998), has: a short name, a full definition, **when to use it, when not to use it**, and an
example. Mayring's qualitative content analysis adds **anchor examples**: the one passage that best shows each code.
Teams check themselves by having two coders code the same passages and measuring agreement (Cohen's kappa), and keep
**memos**: notes on why a code was made or changed.

Recent tools put a language model in the second coder's seat: LLMCode ([2025](https://arxiv.org/html/2504.16671v1))
measures how well the model's codes line up with the researcher's; CollabCoder, LATA
([Wang et al., CSCW 2025](https://www.eecis.udel.edu/~mlm/docs/2025-Wang-CSCW-LATA-Paper.pdf)) and others let the model
propose codes and the person accept, edit or reject them. A common finding: models are good at applying a codebook
with clear criteria, weaker at inventing one.

**For us:** our scope notes are half a codebook entry. Add two fields: **"not this"** (what looks like the motif but
isn't, often the near neighbor a person said "not the same" to) and an **anchor claim** (the person picks the best
example). Both feed the filing judge, which is shown each motif's note and claims already. We already measure
model-person agreement (the motif check); report it as a running number.

### 2. Concept induction: categories defined by a criterion

**LLooM** ([Lam et al., CHI 2024](https://hci.stanford.edu/publications/2024/Lam_LLooM_CHI24.pdf),
[code](https://github.com/michelle123lam/lloom)) turns a pile of texts into high-level concepts, each defined by an
explicit **inclusion criterion** written as a question. The model then scores every text against every concept's
criterion, so a concept's members can be checked, and concepts can be merged or generalized into higher-level ones.
It beat topic models on quality and coverage; in one political dataset it surfaced "attacks on out-party stances",
which experts hadn't noticed.

**TopicGPT** ([Pham et al., NAACL 2024](https://aclanthology.org/2024.naacl-long.164.pdf)) does the same with topics:
generate from a sample, then **refine** by merging near-duplicates (pairs above an embedding similarity, confirmed by
the model) and removing topics that are too rare, then **assign** each document to a topic with a supporting quote.

**For us:** write each motif's scope note so it works as a criterion ("a claim that a politician says what voters
want to hear and then doesn't do it"). Then an **outlier view** per motif: the model applies the criterion back to
each of the motif's claims and lists the ones that don't fit, for the person to move or unfile. TopicGPT's refine step
is our merge suggestions; its "supporting quote" rule is the Focus Group support check we just added.

### 3. Building the hierarchy bottom-up

**Clio** ([Anthropic, 2024](https://www.anthropic.com/research/clio)) clusters many conversations, has a model name
and describe each cluster, then clusters the clusters into a **multi-level hierarchy**, again named by the model, for
people to explore from the top down. Taxonomy builders in HCI do the same with the person approving each step:
Taxonomy Builder ([2022](https://aclanthology.org/2022.hcinlp-1.1.pdf)) ranks candidate new nodes and lets
the user add, edit, delete or skip them; GreenMine ([2025](https://arxiv.org/html/2502.05731v1)) adds charts of where
the model is unsure. "To Classify is to Interpret" ([2023](https://arxiv.org/html/2307.16481)) is a useful warning:
building a taxonomy is interpretation, and the tool should keep the person's reasons, not just their choices.

**For us:** the map's "kinds" tree grows only when a person says "kind of". The model could **propose parents**:
cluster motifs by their notes and claims, name each cluster as a broader motif, and offer it on the map ("these 5 look
like kinds of *Politicians' empty promises*: accept?"). That's the Oct 12 review's question (what shape did the catalog
take?) answered with a draft to react to.

### 4. Interactive topic modeling: the person's moves as constraints

In **interactive topic modeling** (Hu, Boyd-Graber, Satinoff & Smith, *Machine Learning*, 2014), the user's feedback
becomes **must-link** and **cannot-link** constraints that the model has to respect when it re-learns. User studies
since (["Why Didn't You Listen to Me?"](https://arxiv.org/pdf/1905.09864), 2019, and Smith et al., IUI 2018) found people lose trust
fast when a system ignores their corrections or undoes them on the next run.

**For us:** every merge is a must-link; every "not the same", "no", reject and no-motif is a cannot-link. We store
them (`not_same`, `not_claims`, the curation log) and the filer respects the hard ones. The cheap, strong next step:
show the judge **the person's own past decisions** for the motifs it's choosing between, as examples ("a person filed
these here; a person said these are *not* this motif"). And never let a nightly job undo a hand decision (we already
keep hand verdicts; keep testing that).

### 5. Moving things to teach the model: semantic interaction

**ForceSPIRE** (Endert et al., ["Semantic Interaction for Visual Text Analytics"](https://faculty.cc.gatech.edu/~aendert3/resources/Endert_CHI2012_Semantic_Interaction.pdf),
CHI 2012) lays documents out by similarity; when the analyst drags two documents together, the system learns which
words made them similar and re-lays out everything. The analyst teaches the model by doing what they'd do anyway.
Newer versions do the same with must/cannot-link clicks on a projection
([IPBC, 2026](https://arxiv.org/html/2601.18828)).

**For us:** the board's drag-and-drop already records decisions; the map could do the same, with dragging a motif onto
another as "related" or "kind of". Making the layout itself learn is a bigger job and probably not worth it at our size.

### 6. Entity resolution: review the uncertain cases first

Deduplication tools face the same "are these the same thing?" question at scale. **dedupe**
([docs](https://docs.dedupe.io/)) uses **active learning**: it shows the person the pairs it is *least sure about*,
relearns after each answer, and stops asking once it's confident. Good review screens show the two records side by
side with differences highlighted, and offer **split** as well as merge.

**For us:** the motif check page could order its queue by **uncertainty**, not age: filings where the judge's pick was
close (two motifs nearly tied), where two models disagree, or where the claim sits far from the motif's other claims.
A person's 20 checks a day then fix the most. We have merge; a **split** (select some claims, make a new motif) belongs
on the board.

### 7. Card sorting and affinity diagrams

UX researchers sort cards into groups (open card sorting; affinity diagrams on a wall or in Miro). Tools like
OptimalSort summarize many sorts with a **similarity matrix** (how often two cards landed together) and a
**dendrogram**. Their working habits match ours: sort fast, name groups late, and revisit the "miscellaneous" pile.

**For us:** a motif × motif matrix of shared claims (we compute shared pairs for the map already) shown as a heatmap is
a quick way to spot merge candidates and muddled boundaries. And a **"miscellaneous" pile** made explicit: the
singletons and no-motif claims, revisited on a schedule (the singles page is most of this).

### 8. Folklore's own indexes

Thompson's *Motif-Index of Folk-Literature* uses letter chapters and decimal numbers so that **a motif's number says
where it sits** (K: deceptions; K1000s: deceptions into self-injury), with "cf." cross-references between related
motifs. The ATU index groups whole tale types the same way. **MOMFER** ([Meertens Institute](https://momfer.meertens.knaw.nl/);
Karsdorp et al. 2015) made Thompson's index searchable by meaning, expanding each search word to its broader terms
(WordNet hypernyms), because people search for "animals" and the index says "ass". Tangherlini's work on conspiracy
narratives ([Bridgegate and Pizzagate pipeline, 2020](https://arxiv.org/pdf/2008.09961)) models a narrative as a network
of actors and relations rather than a list of motifs, which suits political stories that combine several motifs.

**For us:** when the kinds tree settles (after Oct 12), number motifs by their place in it, Thompson-style, so an id
says what family a motif belongs to; keep the flat M-numbers as stable ids. Our motif search should match by meaning
(embeddings already do) and by the notes' words. Tangherlini's actor-relation framing is the natural next layer for
motifs that are really stories ("X betrays Y to help Z").

### 9. Thesaurus standards: SKOS

Libraries and digital humanities projects publish vocabularies in **SKOS** (W3C's Simple Knowledge Organization System):
each concept has a `prefLabel`, `altLabel`s, `broader` / `narrower` / `related` links, a `scopeNote`, an
`editorialNote`, and `exactMatch` / `closeMatch` links to other vocabularies. Tools such as VocBench (editing) and
Skosmos (browsing) work with it.

**For us:** our index already has nearly this shape (names, kinds, related, scope notes, notes by whom). An export to
SKOS would let other researchers load the BND Motif Index into their tools and link our motifs to Thompson's numbers
(`closeMatch`), which fits the digital humanities side of the project (#146).

### 10. Exploring the unfiled pile: Scatter/Gather

**Scatter/Gather** (Cutting, Karger, Pedersen & Tukey, SIGIR 1992) browses a collection by clustering it, letting the
person pick the interesting clusters, and clustering just those again, a few rounds down. It's built for "I don't
know what's in here yet".

**For us:** a view of the claims with no motif and the singletons that clusters them a few levels deep, so a person can
spot a motif that hasn't been named yet ("these 9 are all about stolen elections in one county").

## What to do, in order

Cheap and likely to help most first. Nothing here is built yet; each is a proposal.

1. **The person's decisions as examples for the judge** (§4): show the filer the claims a person filed in, and said
   were not in, the candidate motifs. Test it on the settled claims like the Oct 5–6 bake-off.
2. **Uncertainty-ordered motif check** (§6): close calls and model disagreements first.
3. **Codebook fields on the notes page** (§1): "not this" and an anchor claim, both shown to the judge.
4. **Outlier view per motif** (§2): claims that fail the motif's note as a criterion, for review.
5. **Split on the board** (§6): select claims, make them a new motif.
6. **Proposed parents on the map** (§3), for the Oct 12 review.
7. **Numbers for the Oct 12 review**: coverage (share of claims with a motif), reuse (claims per motif; singleton
   share), model–person agreement over time, merges and splits per week (§1, §7).
8. Later: motif × motif heatmap (§7), Scatter/Gather on the unfiled pile (§10), SKOS export with Thompson links (§9),
   Thompson-style numbering once the tree settles (§8).

## Sources

- MacQueen, McLellan, Kay & Milstein, "Codebook Development for Team-Based Qualitative Analysis", *Cultural
  Anthropology Methods* 10(2), 1998.
- Mayring, *Qualitative Content Analysis* (2000 article; 2014 open-access book).
- Lam, Teoh, Landay, Heer & Bernstein, "Concept Induction: Analyzing Unstructured Text with High-Level Concepts Using
  LLooM", CHI 2024. <https://dl.acm.org/doi/10.1145/3613904.3642830>
- Pham, Hoyle, Sun, Resnik & Iyyer, "TopicGPT: A Prompt-based Topic Modeling Framework", NAACL 2024.
  <https://aclanthology.org/2024.naacl-long.164.pdf>
- Tamkin et al., "Clio: Privacy-Preserving Insights into Real-World AI Use", Anthropic, 2024.
  <https://www.anthropic.com/research/clio>
- Hu, Boyd-Graber, Satinoff & Smith, "Interactive Topic Modeling", *Machine Learning* 95, 2014.
- Smith, Kumar, Boyd-Graber, Seppi & Findlater, "Closing the Loop: User-Centered Design and Evaluation of a
  Human-in-the-Loop Topic Modeling System", IUI 2018; and "Why Didn't You Listen to Me? Comparing User Control of
  Human-in-the-Loop Topic Models", 2019.
  <https://arxiv.org/pdf/1905.09864>
- Endert, Fiaux & North, "Semantic Interaction for Visual Text Analytics", CHI 2012.
- dedupe documentation (active learning for entity resolution). <https://docs.dedupe.io/>
- Cutting, Karger, Pedersen & Tukey, "Scatter/Gather: A Cluster-based Approach to Browsing Large Document
  Collections", SIGIR 1992.
- Karsdorp, van der Meulen, Meder & van den Bosch, "MOMFER: A Search Engine of Thompson's Motif-Index of Folk
  Literature", *Folklore* 126(1), 2015. <https://momfer.meertens.knaw.nl/>
- Tangherlini, Shahsavari, Shahbazi, Ebrahimzadeh & Roychowdhury, "An automated pipeline for the discovery of
  conspiracy and conspiracy theory narrative frameworks: Bridgegate, Pizzagate and storytelling on the web", 2020.
  <https://arxiv.org/pdf/2008.09961>
- W3C, *SKOS Simple Knowledge Organization System Reference*, 2009.
- "Taxonomy Builder: a Data-driven and User-centric Tool for Streamlining Taxonomy Construction",
  HCI+NLP workshop 2022. <https://aclanthology.org/2022.hcinlp-1.1.pdf>
