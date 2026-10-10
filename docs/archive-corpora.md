# Archive corpora: what's open for older tellings

Which older corpora could the filing pipeline read, and in what order? This note surveys what is openly available
and machine-readable, for experiment A5 in the queue (after A2, the American Stories test). Researched Oct 10, 2026:
four web passes, a few dozen requests each, spaced 10–30 s per site, nothing downloaded. Prompted by Jesse Waites,
"I pointed AI at 400 years of archives" (Oct 2026), which ran a filter-then-read pipeline over the GLOBALISE
transcriptions of the Dutch East India Company (VOC) archive.

The same rules as A1–A4 apply: archive text is a validator and a source of lineage, never mixed into our database or
check queue (own data dir, a copy of the index); downloads need the person's OK with sizes; the GPU under the lease.

Marks: **V** = read on the source page; **S** = from search results only (unchecked); **I** = inferred.

## Is modern OCR much better?

Yes, by roughly five to ten times on early modern print, but it fails in a new way.

- **Old OCR** (what Google Books, HathiTrust, Internet Archive and ECCO mostly carry): ABBYY at about 85%
  character accuracy on historical roman type (Springmann 2014, S); ECCO about 22% word error (Hill & Hengchen, S);
  stock Tesseract 20.9% character error on 1612–1807 print (V, below).
- **Period-trained engines**: Transkribus's Noscemus GM 6 for early modern Latin print, 0.8% CER on its validation
  set (V; platform-only, credits); Calamari trained per book on GT4HistOCR, 0.44% (S). A re-OCR of 498 titles
  1600–1800 (mostly Google scans) with trained Tesseract reached 90–95% word accuracy (DSH 37/4, 2022, V).
- **Vision-language OCR**: on early modern print 1612–1807 (probably English), Gemini 3.5 Flash 2.15% CER, Chandra 2
  and Infinity Parser 2 about 2.6%, olmOCR 2 4.27%
  ([critical-search benchmark, Jul 2026](https://working-papers-in-critical-search.github.io/paper-004-ocr-benchmark/), V).
  On 18th–19th-century books in English, French, German and Latin, dots.mocr (3B) 97.6 accuracy, PaddleOCR-VL 96.1,
  olmOCR-2 95.7 ([FineBooks leaderboard, Aug 2026](https://huggingface.co/blog/finebooks/historical-books-ocr-leaderboard), V).
- **The new failure**: VLMs "silently modernise" spelling, smooth over abbreviations and long s, and sometimes write
  fluent text that isn't on the page (general VLMs rewrite up to 6.9 WER points under perturbation, OCR-specialist
  ones 0.1–3.4, classic OCR under 0.8; [arXiv 2607.21617](https://arxiv.org/abs/2607.21617), V). LLM post-correction
  made historical OCR worse in one study ([arXiv 2510.06743](https://arxiv.org/abs/2510.06743), V). For filing tellings
  a 3B OCR model is enough; anything quoted as evidence must link to the page image, and a classic engine's output
  kept beside it shows where the VLM guessed.
- **Gaps**: no benchmark tests Latin before 1600. Handwriting is another matter: Persian nastaliq manuscripts are
  unread by any open model (below).
- **Fits the 10 GB card**: dots.ocr/dots.mocr (~3B, peaks 7.9 GB), PaddleOCR-VL (1B), GLM-OCR and OvisOCR2 (0.9B),
  Qwen3-VL-4B, Qwen3-VL-8B at 4-bit; Kraken, Calamari, Tesseract trivially. olmOCR wants 12 GB (Q4 GGUF builds ~8 GB, S).

## Early modern news (first)

The open, ready text is in printed Dutch, German and English news. The manuscript newsletters (Fugger, avvisi) are
images, or text held back on request.

| Corpus | Language, dates | Scale | Text? | Licence | Access |
|---|---|---|---|---|---|
| [Delpher open newspaper archive](https://www.delpher.nl/over-delpher/delpher-open-krantenarchief/download-teksten-kranten-1618-1879) (KB) | Dutch, 1618–1879 | 1618–1699 zip: 8,559 issues, 1 GB (5.3 GB unpacked) | OCR + ALTO; volunteers re-keyed ~6,000 17th-c. issues (18M words), said to be on Delpher | public domain past 140 years (S) | bulk zip (S; page refused our fetcher) |
| [Couranten Corpus](https://ivdnt.org/corpora-lexica/courantencorpus/) (INT) | Dutch, 1618–1700 | 13 papers, 109,532 articles, 18.9M words | hand-transcribed, lemmatized, genre-tagged | none stated | online search only; data by request (V) |
| [Deutsches Textarchiv](https://www.deutschestextarchiv.de/list/browse?genre=Zeitung), newspapers | German, 1609–1750 | 17 titles before 1750, mostly sample years (1609 *Relation* and *Aviso*, Hamburg *Correspondent* 1712–25…) | clean TEI | CC BY-SA 4.0 (S) | bulk TEI zips, 361–537 MB for the whole archive (S) |
| [Lancaster Newsbooks](https://huggingface.co/datasets/biglam/lancaster_newsbooks) | English, 1653–55 | 303 London newsbooks | hand-keyed | CC BY-NC-SA 3.0 | Parquet on HF (V) |
| [EEBO-TCP](https://earlyprint.org/intros/intro-to-eebo-and-eebo-tcp.html) | English (some Latin), to 1700 | ~60k texts | hand-keyed | public domain (Phase I 2015, II 2020; V) | bulk via TCP/Oxford Text Archive; **periodicals left out**, one-off news pamphlets in (I) |
| [Gazette de France](https://gallica.bnf.fr/ark:/12148/cb32780022t/date) | French, 1631–1792 | weekly | OCR (~88% estimated) | free non-commercial reuse with credit (S) | Gallica API, paced; no bulk |
| [Euronews XML corpus](https://zenodo.org/records/5524182) (UCC + Medici Archive Project) | Italian avvisi, 1550–1730 | test case a full year (1600) | transcribed XML | none shown | **restricted**, by request (V) |
| [Fuggerzeitungen](https://fuggerzeitungen.univie.ac.at/en/about-fugger-newsletters) (ÖNB) | German 82%, Italian 17%; 1568–1605 | ~15,000 newsletters | facsimiles + index of ~10k people, 5.5k places; no transcription | none stated | images only (V); a 1923 printed selection is on [Internet Archive](https://archive.org/details/fuggerzeitungenu00klaruoft) |
| Vatican avvisi (Urb. lat. 1038–1112) | Italian, 1554–1648 | 75 volumes | images | — | DigiVatLib (S) |
| [Wickiana](https://www.zb.uzh.ch/en/news/wickiana) (Zurich) | German, 1559–88 | 24 vols of wonder and news reports | "some" transcribed | not checked | e-manuscripta.ch (S) |
| *Mercurius Gallobelgicus* | Latin, 1592–1635 | semiannual | scans, raw OCR | public domain | [HathiTrust](https://catalog.hathitrust.org/Record/009313814), Google Books (S) |
| [Relaciones de sucesos (CBDRS)](https://www.bidiso.es/CBDRS/) | Spanish, 16th–18th c. | 5,219 works, 1,607 copies digitized | "some" transcribed | none found | no bulk (S) |
| ZEN (Zurich English Newspapers) | English, 1661–1791 | 349 issues, 1.6M words | hand-keyed TEI | — | CD/email request (S) |
| EMLO | letter metadata | — | little text | no bulk "without explicit permission" (S) | — |

The best bet is the **Delpher 1618–1699 zip**: Amsterdam was where Europe's news met, and the corantos report the
whole continent week by week. First check one 1632 issue against the Couranten text to see whether the zip carries
the corrected transcriptions or the raw gothic-type OCR (I). Then the **DTA papers** for the same weeks give a German
side, to follow one report across languages; **Lancaster and EEBO-TCP pamphlets** give English wonders and "true
relations", close to the motif index's home ground.

## Neo-Latin (the person's favourite)

| Corpus | What | Scale | Text? | Licence | Access |
|---|---|---|---|---|---|
| [CAMENA](https://github.com/nevenjovanovic/camena-neolatinlit) | Latin printed in German lands, ~1500–1770: poems, history and politics, reference works, letters (CERA 1530–1770) | 1,751 files, ~50.5M tokens | clean XML ("not all files provide full text") | CC BY-SA 4.0 | GitHub (V) |
| [Noscemus Digital Sourcebook](https://zenodo.org/records/15040256) | ~1,000 early modern Latin science works | 301 MB zip | raw Transkribus output, uncorrected | CC BY 4.0 | Zenodo (V) |
| [NOSCEMUS ERASMUM](https://zenodo.org/records/17515929) | Erasmus, Leiden *Opera omnia* (1703–06), 11 vols | — | Transkribus, being corrected | CC BY 4.0 | Zenodo (V) |
| [CKCC / ePistolarium](https://ckcc.huygens.knaw.nl/?page_id=43) | letters of Dutch Republic scholars (Grotius, Huygens, Descartes) | ~20,000 letters, 32.8% Latin | TEI | none stated on the corpus page | [Zenodo dump](https://doi.org/10.5281/zenodo.6631385) (S; full text unchecked) |
| [Corpus Corporum](https://mlat.uzh.ch) | mostly patristic and medieval, some Neo-Latin | ~226M words | TEI/txt | CC BY-NC-SA 4.0, mixed (S) | per text; an HF copy claims public domain, contradicting it |
| [Source Library](https://sourcelibrary.org/about) | alchemy, Hermetica, early science | 42,298 books | Gemini OCR + machine translation | originals PD, translations CC BY-SA 4.0, "AI training requires a license" | API, MCP (V) |
| [PleIAs/Latin-PD](https://huggingface.co/datasets/PleIAs/Latin-PD) | Latin printed before 1884 | 16.5B words, 159,070 titles, dated | old raw OCR | public domain | Parquet on HF (V) |
| [The Latin Library](https://www.thelatinlibrary.com/neo.html) | ~70 Neo-Latin authors | — | clean | none stated | mirrored by CLTK |

The genres closest to the motif index exist only as scans with old OCR: Lycosthenes' *Prodigiorum ac ostentorum
chronicon* (1557; [Internet Archive](https://archive.org/details/BIUSante_01429), 683 pp.), the printed Jesuit
*Annuae litterae* 1581–1654 ([Internet Archive](https://archive.org/details/annulitersocieta00jesu_0)), and
*Mercurius Gallobelgicus*. They make a small re-OCR experiment: dots.mocr or Qwen3-VL against Kraken, scored on a
few hand-transcribed pages (Noscemus's uncorrected Transkribus text is a ready comparison).

Translation: GPT-4 scored BLEU 34.5 against Google's 7.4 on 16th-century Bullinger letters
([Volk et al. 2024](https://aclanthology.org/2024.lt4hala-1.15/), S); no evaluation of open local models on
Neo-Latin was found.

## Persian: needs digitizing first

No Persian-language news source is searchable as text today. The akhbarat (Mughal court newsletters,
[Royal Asiatic Society](https://royalasiaticcollections.org/akhbarat-archive/): 2,777 folios, 1660–1709, shikasta,
images for research use only, V), the state gazette *Vaqaye'-e Ettefaqiyeh* (from 1851,
[Wikimedia Commons](https://commons.wikimedia.org/wiki/Category:Vaqaye'-e_Ettefaqiyeh), ~3,100 lithographed
nastaliq pages, V), and the [Princeton](https://dpul.princeton.edu/menam/feature/pre-1979-persian-newspapers-collection)
and Bonn periodicals are all images. Lithographed nastaliq is a handwriting problem, not a print one.

Reading it: OpenITI's Kraken models do well on printed Persian (CER from over 20% to under 3% on the top typefaces,
S); for nastaliq manuscripts, a test dated Oct 1, 2026 found Gemini Flash at 0.70 median sequence accuracy with
meaning-changing errors, and no Kraken model at all
([sourcelibrary issue 5559](https://github.com/Embassy-of-the-Free-Mind/sourcelibrary-v2/issues/5559), V). Open
ground truth is a few hundred pages under non-commercial licences (OpenITI MAKHZAN, HPMD). A pilot would mean
hand-transcribing 1,000–3,000 lines and fine-tuning: weeks of a paleographer's time per script.

Meanwhile the Persian world can be read through English and Dutch reporting:

- **Calendar of Persian Correspondence**: English summaries of letters between East India Company officials and
  Indian rulers, 1759–~1795, OCR'd on Internet Archive (e.g. [vol. 7, 1785–87](https://archive.org/details/calendarofpersia07indi), V).
  Full of reports, rumors and court intrigue; no digitizing needed.
- **[Qatar Digital Library](https://www.qdl.qa)**: India Office Records on the Gulf, ~475k pages, mid-18th century to
  1951, with "News and Intelligence Summaries" files; OCR for typewritten English only; Crown-copyright items under
  the Open Government Licence, others restricted; IIIF manifests, no bulk text (S; the site refused our fetcher).
- **[GLOBALISE](https://globalise.huygens.knaw.nl/project_overview/)**: ~5M pages of VOC letters, machine-transcribed,
  scans CC0 and transcriptions CC0 per search results, on [DataverseNL](https://dataverse.nl/dataverse/globalise)
  (V). The company kept a post in Persia; the archive Waites used.

Literary Persian is open ([Persian Digital Library](https://github.com/PersDigUMD/PDL), CC BY-SA 4.0, V; Ganjoor) but
isn't news.

## Ancient

Correction to what was said in chat on Oct 10: **ORACC's bulk JSON has no translations** ("Translation is not
included", per its COMPASS guide, V); English comes from the HTML text pages. Licence: CC BY-SA 3.0 on the SAAo and
ADsD pages (V), though the JSON is described as CC0.

| Corpus | What | Scale | English? | Licence |
|---|---|---|---|---|
| [SAAo](https://oracc.museum.upenn.edu/saao/) (State Archives of Assyria) | Neo-Assyrian royal correspondence and more | 5,056 texts, ~2,600 letters (SAA 1, 5, 10, 13, 15–19, 21) | all 21 volumes (V) | CC BY-SA 3.0 |
| [ADsD](https://oracc.museum.upenn.edu/adsd/) (Astronomical Diaries) | sky, prices, river, weather, then events and reports | ~1,000 tablets, ~650–60 BCE; historical sections fuller from the 4th c. BCE | line by line (V) | CC BY-SA 3.0 |
| [papyri.info / idp.data](https://github.com/papyri/idp.data) | documentary Greek papyri | ~55,000+ texts | partial (many HGV translations are German) | CC BY 3.0 (V) |
| RINAP / RIAo / RIBo | royal inscriptions: the official telling, against the letters | — | yes | CC BY-SA 3.0 |
| [CDLI](https://cdli.earth) | catalogue of 390–400k inscriptions | — | a minority (I) | none found; GitHub dump stale since Aug 2022, API current |
| [eBL](https://doi.org/10.5281/zenodo.10018951) | Babylonian literature and fragments | ~25,000 tablets | none in the data | CC BY-NC-SA 4.0 |
| Old Assyrian (Kültepe) letters | merchant letters, ~23,500 tablets | ~5,700 digitized (S, unverified) | thin | unclear; not on ORACC |
| [ETCSL](https://etcsl.orinst.ox.ac.uk) | Sumerian literature | ~400 compositions | yes | none stated; unmaintained since 2006 |
| [Perseus canonical-greekLit](https://github.com/PerseusDL/canonical-greekLit), First1KGreek | Greek literature | — | some | CC BY-SA 4.0 |

Machine translation of Akkadian is a first draft at best: Gutherz et al. 2023 scored BLEU 37.5, but experts rated
only 44% of sampled sentences proper translations and 16% hallucinated (V). The field is crowded on tools
(translation, OCR, fragment joins, a 2,674-team Kaggle challenge on Old Assyrian translation, Dec 2025–Mar 2026) and,
as far as the search found, empty on reading letters' content as rumor or narrative motifs (I).

## Wildcards

- **Portuguese Inquisition**: ~40,000 trial records on [digitarq](https://digitarq.arquivos.pt), images; the
  TraPrInq project transcribed 5,000 pages and trained a 7.84% CER Transkribus model, transcriptions unpublished (V).
  Mexico's AGN Inquisición is images only; nothing found for Venice.
- **Chinese local gazetteers**: 410 rare Harvard-Yenching gazetteers hand-keyed (over 99% accurate) in
  [LoGaRT](https://logart.mpiwg-berlin.mpg.de/), CC BY-NC-ND 4.0, search results export to CSV; bulk unclear;
  portents sections not tagged as far as we could tell (V).
- **Ottoman**: a public Transkribus model for 19th-century periodicals at 7.2% CER
  ([Digital Ottoman Corpora](https://www.digitalottomancorpora.org/copy-of-htr-1), V); no large open transcribed set.

## Controls: known events to find first

Before trusting what a search doesn't find, prove it finds what is known to be there (Waites's rule, as in A2).
Lepanto (Oct 1571; Fugger, avvisi), the comet of 1577 (Wickiana, German pamphlets), the Armada (1588, EEBO-TCP), the
Defenestration of Prague (May 1618, the first Dutch corantos that June), Gustavus Adolphus's death at Lützen (Nov
1632, wide rumor variance across Dutch, French and German papers), Charles I's execution (1649), the Great Fire of
London (1666), the siege of Vienna (1683). Fixed dates also measure how fast news travelled and how it changed
between languages. For the ancient sets, eclipses in the Diaries can be computed.

## Suggested order

1. **Delpher 1618–1699 + DTA newspapers** (Dutch and German, same weeks): the method across languages; Lützen 1632
   as the first control. Resolve first whether the Delpher zip has the corrected text.
2. **CAMENA** (Neo-Latin, clean, CC BY-SA): letters and *historica et politica* first.
3. **Lancaster newsbooks + EEBO-TCP wonder pamphlets** (English).
4. **A re-OCR test** on Lycosthenes or the *Annuae litterae*: a local 3B OCR model against Kraken, a few pages
   hand-checked.
5. **SAAo letters and the Astronomical Diaries** (English translations, CC BY-SA).
6. Later or by request: Euronews avvisi (email UCC), Couranten Corpus data (ask INT), GLOBALISE, Calendar of Persian
   Correspondence; Persian-language sources only with a digitizing project.

Questions to settle before any download: the Delpher zip's contents; the Couranten Corpus and CKCC licences;
whether the person wants to email UCC or INT for data.
