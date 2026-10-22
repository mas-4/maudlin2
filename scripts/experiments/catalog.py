"""The experiments' catalog (Oct 11, the person: "make sure you keep all these different experiments and their data
production curated and catalogued with sqlite databases etc. i'd rather not have 1gb json files"). One SQLite file,
experiments.sqlite, beside the experiments' data:

    experiments  code -> name, family, question, script, status, data (where its data lives), result (in a line)
    results      every result line an experiment reported (harness.note writes here too), by code and time
    files        every file in the experiments' folder, with its size and the experiment it belongs to

The data itself lives in databases: the archive experiments' documents, claims, filings and motifs in
archives/archives.sqlite (archive_db.py); what's left in the experiments' folder is small resume state and caches,
listed here with their sizes so nothing big hides.

    catalog.py sync     the registry below, the result log and the folder's files into the catalog
    catalog.py show     the catalog, newest first"""
import os
import re
import sqlite3
import sys
from datetime import datetime as dt

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

DB = os.path.join(harness.EXP, 'experiments.sqlite')
ARCHIVES = 'archives/archives.sqlite'
SCHEMA = """
create table if not exists experiments (code text primary key, name text, family text, question text, script text,
    status text, data text, result text, updated text, codename text, why text);
create table if not exists results (at text, code text, line text, unique (at, line));
create table if not exists files (path text primary key, code text, bytes integer, modified text);
"""
FAMILIES = {'E': 'the shortlist: finding a claim\'s motifs', 'J': 'the judge', 'C': 'a cascade', 'R': 'the reranker',
            'W': 'wording claims', 'G': 'genre and group descriptions', 'M': 'one model for another',
            'P': 'proposals and praxis', 'D': 'ideas from the research', 'A': 'archives: our method on outside material',
            'S': 'stories and sagas', 'F': 'filing: fewer corrections for the person', 'U': 'the machine alone, without curation', 'ASR': 'transcription'}
# code: (name, script, status, data, result)
REGISTRY = {
    'A1': ('Our pipeline on 1,518 ATU-labelled folktales', 'a1_folktales.py', 'answered',
           'a1_folktales.json; archives/trilogy', 'right type in the shortlist ~9 in 10, picked 4 in 5, judge AUC 0.93-0.95'),
    'A2': ('The 1896 newspapers: does filing hold up off-distribution; controls', 'a2_newspapers.py', 'answered',
           f'{ARCHIVES} (american_stories_1896: 413,186 articles; claims, filings); a2_newspapers.json (resume state)',
           '96% filed, 40% sure; 24 new motifs (5% of filings); conspiracy controls read as class conflict; spot-check pending'),
    'A3': ('Viral Texts: do reprints of one piece file alike?', 'a3_viral_texts.py', 'answered',
           f'{ARCHIVES} (viral_texts_1836_1861: 49,999 reprints); a3_viral_texts.json (resume state)',
           'copies of one piece file alike: Jaccard 0.32 within against 0.03 between; a shared motif in 59%'),
    'A4': ('Greek and Roman speeches (Catilinarians the control)', '', 'planned', 'archives/speeches', ''),
    'A5': ('Early modern news: Delpher 1618-99, Lancaster newsbooks', '', 'planned',
           'archives/delpher (1618-99 zip, 1.1 GB); archives/lancaster_newsbooks (1653-55, 303 XML files, CC BY-NC-SA 3.0)', ''),
    'A6': ('LOCO: conspiracy against matched mainstream documents, a control', '', 'planned', '', ''),
    'A7': ('The Congressional Record 1873-2011: motifs over 140 years', '', 'planned', '', ''),
    'A8': ('The Q drops: do their shapes meet 1896\'s?', '', 'planned', '', ''),
    'A9': ('ClaimsKG: does one claim file alike across fact-checkers?', '', 'planned', '', ''),
    'D1': ('Does the judge read the must-have element?', 'd1_definition_swap.py', 'answered', 'd1_definition_swap.json',
           'yes: AUC 0.821 with its own element, 0.64-0.65 with another motif\'s'),
    'D2': ('Show the judge the person\'s past removals?', 'd2_past_verdicts.py', 'unproven', 'd2_past_verdicts.json',
           'AUC 0.796 to 0.809, within the noise'),
    'D3': ('Simulated annotators: does agreement say when to trust the judge?', 'd3_simulated_annotators.py', 'not kept',
           'd3_simulated_annotators.json', 'no: the confidence model stays at AUC 0.885'),
    'D4': ('Tell-Tale Hat: which motifs overlap or drift', 'd4_tell_tale_hat.py', 'your call', 'd4_tell_tale_hat.json',
           '22 candidate pairs, 6 drifting motifs'),
    'D5': ('Tangherlini\'s actants as signals', 'd5_actants.py', 'not kept', 'd5_actants.json; signals_d5.pkl',
           'strong alone (AUC 0.899) but the embeddings already carry it'),
    'E12': ('Seed motifs in the shortlist (from A1)', 'e12_seed_shortlist.py', 'answered', 'e12_seed_shortlist.json',
            'not buried: a quirk of the weights lifts motifs with no claims'),
    'E13': ('A fuller telling for finding a claim\'s motifs (from A1)', 'e13_richer_telling.py', 'answered',
            'e13_richer_telling.json', 'claim and telling together: right motif in the top 12 68% to 73% (top 8 63% to 69%)'),
    'P2': ('The Oct 10 praxis: the judge\'s question and the naming rules', 'p2_praxis_oct10.py', 'in production',
           'p2_praxis_oct10.json', 'naming rules live Oct 10'),
    'P2b': ('The naming rules without a leading "The"', 'p2b_no_the.py', 'your call', '', 'house style kept'),
    'S1': ('A new event or the same one updated?', 's1_story_splits.py', 'answered', 's1_story_splits.json; s1_doc_rows.json',
           'Gemma agrees 78%, Nimble 60%'),
    'S2': ('Re-sorting a saga\'s headlines into parts', 's2_saga_resort.py', 'not yet', 's2_*.json',
           'three dry runs: k-means plus merging lumps or splits wrongly'),
    'S3': ('What makes headlines one story: TF-IDF, embeddings or hybrids', 's3_story_similarity.py', 'answered',
           's3_story_similarity.json; s3_day.json',
           'precision at equal coverage: TF-IDF 0.25-0.64, mxbai 0.88, hybrids 0.92-0.95; recall sample too small (3)'),
    'S4': ('Seams in stories: embeddings, then TF-IDF cuts', 's4_story_seams.py', 'answered', 's4_story_seams.json',
           'cuts scoring under 0.6 right 18 of 18, 0.6-0.7 69%, over 0.8 rarely'),
    'S5': ('A long story split at each new development, replayed over every story of 36 hours or more',
           's5_sinbad.py', 'answered', 's5_sinbad.json',
           'not as asked: 54% of long stories split, 10.6% into 5+ parts; caught 4 of 5 known developments but missed the Fort Hood cancellation; blind verdicts pending'),
    'F1': ('Splitting motifs where they hold two tellings: Atropos\'s word cut on motifs', 'f1_gordian_knot.py',
           'answered', 'f1_gordian_knot.json; curation.sqlite (the index\'s versions)',
           'no: words can\'t see it (odd one out 11% against chance 14%; cut AUC 0.67)'),
    'F2': ('The motifs the machine missed: was your "also" in the shortlist?', 'f2_cerberus.py', 'answered',
           'f2_cerberus.json', 'half: the motif added in the top 12 50%, top 40 72% (the one chosen 56%, 86%; plain weights)'),
    'F3': ('A fixed yardstick: 200 held-out decisions, weighed weekly', 'f3_maat.py', 'in production',
           'maat_set.json; maat_history.json', 'weekly; Oct 18: first set AUC 0.915, the torn set 0.809'),
    'F7': ('Can the machine tell when nothing fits, and propose instead of forcing?', 'f7_procrustes.py', 'answered',
           'f7_procrustes.json', 'best shortlist fit spots nothing-fit at AUC 0.84; a line near 0.7 catches half, 9% of fits'),
    'F4': ('A telling abstracted as the proverb it is an instance of', 'f4_abstract_tellings.py', 'answered',
           'f4_abstract.sqlite; f4_abstract.json', 'no: alone 20% at top 12 against plain 71%; summed with plain, -17 points'),
    'F5': ('A telling abstracted as the same story told about three other subjects', 'f4_abstract_tellings.py', 'answered',
           'f4_abstract.sqlite; f4_abstract.json', 'no: alone 41% at top 12; summed with plain, -6 points'),
    'F6': ('A telling abstracted as its rhetoric: stasis, driver, time shape, speech act', 'f4_abstract_tellings.py',
           'answered', 'f4_abstract.sqlite; f4_abstract.json',
           'yes: same-motif pairs share a speech act +18 points, a stasis +13; carved claims stand out; next: as confidence features'),
    'F8': ('Are claims from posts several tellings stitched into one?', 'f8_chimera.py', 'answered', 'f8_chimera.json',
           'yes, nearly all: ~4 claims a group, 3+ motif and one-motif groups alike; motifs on different sub-claims 46 of 59'),
    'F9': ('Single posts filed on their own, then grouped by motif', 'f9_isis.py', 'answered', 'f9_isis.json',
           'single posts reach 79.5% of the person\'s motifs, 74.5% land in them; layered beat stitched 75 to 3'),
    'F10': ("Pandora: the tellings inside the person's biggest motifs (a dry run)", 'f10_pandora.py', 'in production',
            'f10_pandora.json', 'all 36 motifs split into 227 tellings; 5 judged (all yes); blind set unjudged'),
    'F11': ("How much the confidence model's leak flatters it", 'f11_danaids.py', 'in production', 'f11_danaids.json',
            'the leak was real and small (about 0.01 AUC); fixed Oct 14'),
    'F12': ('The shortlist forward: what each new claim is shown, against the final word', 'f12_prometheus.py',
            'running', 'motifs/shortlist_log.jsonl', 'weekly; 1st week: 56% shown, 19% existed unshown, 25% made later'),
    'F13': ('Seeds let into the shortlist', 'f12_prometheus.py', 'running', 'motifs/shortlist_log.jsonl',
            'weekly; 1st week: a seed shown for 55% of real claims, picked for 2%; 1 of 5 kept so far'),
    'F14': ('Bootstrap intervals in the harness; the Oct 8-10 gains read again', 'f14_tyche.py', 'answered',
            'f14_tyche.json', 'Babel clears the noise (+2.9, +1.7 to +4.2); Matryoshka did on Oct 8 but adds 0.2 now; '
            'the Pleiades inside the fold-split noise'),
    'F15': ('Recall by motif size, and the alike floor', 'f15_thumbelina.py', 'answered', 'f15_thumbelina.json',
            'a leak: one-claim motifs found 100% held out; without it top 12 86.7% to 72.7% (84.8% on motifs of 2+); '
            'two-claim motifs 68%; the floor costs 0.7%'),
    'F16': ('The taught reranker against the untaught, at each teaching and forward', 'f16_magic_mirror.py',
            'in production', 'f16_magic_mirror.json; motifs/reranker/taught.json',
            'no better: untaught 0.776 vs taught 0.758 held out, 0.738 vs 0.739 forward; teaching keeps the winner'),
    'F17': ("The checker's suggestions from the learned shortlist, as filing", 'f17_castor_pollux.py', 'in production',
            'f17_castor_pollux.json', "the person's hand-added motif among the 12 candidates 62.9% to 68.4% "
            '(+3.0 to +9.0); 4.7 of 12 change'),
    'F18': ("The Brothers Grimm's winning wording in every claim prompt, measured forward", '', 'in production',
            'motif index (claims, corrections); app/claim_wording.py',
            'Oct 21: posts 20.7 to 15.9 words; fact-checks not shorter; rewording fall confounded'),
    'F20': ("The claim writer shown the group's most varied posts, not ten at random", 'f20_blind_men.py', 'not kept',
            'f20_blind_men.json', 'varied ten no better than random (65% about each); split covers 79% but 3.6 claims'),
    'F19': ("A telling as its course of action, no topic (SemEval 2026 Task 4's recipe), beside Aesop",
            'f4_abstract_tellings.py', 'answered', 'f4_abstract.sqlite; f4_abstract.json',
            'no: alone 38% at top 12; summed with plain, -5 points'),
    'F21': ('Straight news as a sink: offered beside the wrong motifs, is it picked where nothing fits?',
            'f21_charybdis.py', 'answered', 'f21_charybdis.json',
            'no: offered, it changes wrong picks on nothing-fit claims by +0.9 points (needed -10); takes half of plain reports'),
    'F22': ('The claim organizer alongside the filing: a claim split where its motifs fall on different posts',
            'f22_psyche.py', 'not kept', 'f22_psyche.json; motif_proposals.json (kinds split, no_split)',
            'splits about a quarter whatever the filing (28% vs 25%); its proposals never reached the person'),
    'F23': ('The note first, then the name: new motifs named after their scope note is written', 'f23_ptah.py',
            'answered', 'f23_ptah.json',
            'no clear gain: names +0.008 likeness, near matches +3.4 points, but 7 points more abstract labels; blind pairs pending'),
    'F24': ('A telling, not a report: a report-or-telling signal and bulk passes counted for less, in the confidence model',
            'f24_munchausen.py', 'answered', 'f24_munchausen.sqlite',
            'not kept: report signals moved nothing (AUC within 0.002); the gate, blind on Oct 19-20, caught 24% (40% asked)'),
    'F25': ("Each motif mirrored in 20 versions (other casts, settings, voices) for the shortlist to catch claims by",
            'f25_indras_net.py', 'answered', 'f25_indras_net.sqlite',
            'not kept: top-12 +0.3 (87.5% to 87.8%); folktales +1.9; versions point right (66%) but say what the note says'),
    'F26': ('The point a teller makes (what they mean, not why), written by Gemma from the claim and from its sources, '
            'as shortlist signals', 'f26_tiresias.py', 'answered', 'f26_tiresias.sqlite',
            'not kept: top-12 +0.3% with sources (interval from -0.0%), +0.0% bare; moves +0.5%; 9 of 159 hard misses back'),
    'F27': ("The tellers' own words: each motif's phrases by weighted log-odds over its tellings, names out, as "
            'shortlist signals', 'f27_ali_baba.py', 'queued', 'f27_ali_baba.sqlite', ''),
    'U1b': ("Golem II: the Golem's broad motifs split by Gemma into the tellings inside", 'u1_uncurated.py split',
            'answered', 'u1_uncurated.json (split); archives/u1',
            '63 motifs became 225; B-cubed precision 0.19 to 0.54, recall 0.53 to 0.44'),
    'U1': ('The machine alone: our filing from an empty index', 'u1_uncurated.py', 'answered',
           f'{ARCHIVES} (runs U1:*); archives/u1 (sandboxes)',
           'it lumps: 63 motifs for 600 claims where you have 465; B-cubed precision 0.19, recall 0.53'),
}
# the earlier ones (Oct 8-10), as the Experiment codes doc has them
for code, name, status, result in [
        ('E0.1', "Gemma's own yes or no", 'not kept', 'AUC 0.818 but overconfident; replaced by Nimble (J1)'),
        ('E0.2', 'An off-the-shelf reranker', 'in production', 'AUC 0.887 with the likenesses and Gemma'),
        ('E0.5', 'Many finders, weighted on the person\'s filings', 'in production', 'the learned shortlist'),
        ('E0.6', 'The confidence model on every signal', 'in production', 'AUC 0.885; the fit on filings'),
        ('E1', "Subtract the day's news from claims and notes", 'in production', 'kept'),
        ('E2', 'Imagined instances of each motif', 'not kept', 'nothing'),
        ('E3', 'Motifs travel in bundles', 'not kept', '82.9% against 82.3%'),
        ('E4', 'A jury of readers', 'not kept', 'nothing'),
        ('E5', "Spread scores over rests-on and related links", 'unproven', 'promising, unproven'),
        ('E6', 'Which order to check in', 'in production', 'least certain first'),
        ('E7', "The layered finder", 'in production', 'kept'),
        ('E8', "The pick prompt showing a motif's nearest claims", 'not kept', 'no difference'),
        ('E9', "The reranker taught the person's taste", 'in production', 'in use'),
        ('E11', 'Every embedding model', 'in production', 'Qwen3-Embedding 8B with Snowflake Arctic 2: top-12 82.3% to 85.2%'),
        ('J1', 'A jury of models for the judge', 'in production',
         'Nimble 9B judges as well as Gemma 26B, faster; second sitting (Oct 17): pplx-decider +0.010, 7x slower, Nimble kept'),
        ('J2', 'The judge as the casebook reasons', 'in production', 'the element won: AUC 0.54 to 0.79'),
        ('C1', 'Small models first, Gemma only when unsure', 'not kept', 'Gemma alone picks with the fewest wrong'),
        ('R1', 'A bigger reranker (4B)', 'not kept', 'not worth it'),
        ('W1', "Writing claims with rules from the person's corrections", 'unproven', 'Gemma closer than Qwen; rules unproven'),
        ('G1', 'Genre descriptions from the praxis', 'in production', 'genre calls right 53% to 64-67%'),
        ('G2', 'Group descriptions for the drafter', 'not kept', 'no help'),
        ('M1', 'Gemma 26B or Qwen3 30B for the match question', 'in production', 'Gemma; the 30B retired'),
        ('P1', 'Nimble scoring the proposals', 'in production', 'ranking AUC 0.772 against 0.755')]:
    REGISTRY.setdefault(code, (name, '', status, '', result))
from codenames import CODENAMES  # noqa: E402  the folklore figures
CODE = re.compile(r'^(E0\.\d|E\d+[a-z]?(?:\+E\d+)?|[A-Z]\d+[a-z]?|ASR|LLM)\b')


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.executescript(SCHEMA)
    return con


def code_of(text: str) -> str:
    m = CODE.match(text.strip())
    return m.group(1) if m else ''


def record(line: str):
    """A result line into the catalog (harness.note calls this)"""
    with connect() as con:
        con.execute('insert or ignore into results values (?, ?, ?)',
                    (dt.now().isoformat(timespec='seconds'), code_of(line), line))


def sync():
    now = dt.now().isoformat(timespec='seconds')
    with connect() as con:
        cols = {r[1] for r in con.execute('pragma table_info(experiments)')}
        for col in ('codename', 'why'):
            if col not in cols:
                con.execute(f'alter table experiments add column {col} text')
        for code, (name, script, status, data, result) in REGISTRY.items():
            family = FAMILIES.get(code.rstrip('0123456789b'), FAMILIES.get(code[0], ''))
            con.execute('insert into experiments values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) on conflict (code) do update set '
                        'name = excluded.name, family = excluded.family, script = excluded.script, status = excluded.status, '
                        'data = excluded.data, result = case when excluded.result != \'\' then excluded.result else result end, '
                        'updated = excluded.updated, codename = excluded.codename, why = excluded.why',
                        (code, name, family, name, script, status, data, result, now, *CODENAMES.get(code, ('', ''))))
        log = os.path.join(harness.EXP, 'results.log')
        if os.path.exists(log):
            for raw in open(log):
                at, _, line = raw.rstrip('\n').partition(' ')
                con.execute('insert or ignore into results values (?, ?, ?)', (at, code_of(line), line))
        con.execute('delete from files')
        for root, _, names in os.walk(harness.EXP):
            for n in names:
                p = os.path.join(root, n)
                if p == DB:
                    continue
                rel = os.path.relpath(p, harness.EXP)
                guess = (re.match(r'([a-z]+\d+[a-z]?)', rel.split('/')[0]) or [None, ''])[1].upper()
                con.execute('insert into files values (?, ?, ?, ?)', (rel, guess, os.path.getsize(p),
                                                                        dt.fromtimestamp(os.path.getmtime(p)).isoformat(timespec='seconds')))
    show()


def show():
    con = connect()
    for code, fig, name, status, result in con.execute('select code, codename, name, status, result from experiments order by code'):
        print(f'{code:5} {fig or "":26} {status:13} {name[:52]:52} {result[:60]}')
    n, size = con.execute('select count(*), sum(bytes) from files').fetchone()
    big = con.execute('select path, bytes from files order by bytes desc limit 5').fetchall()
    print(f'\n{con.execute("select count(*) from results").fetchone()[0]} result lines; {n} files, {size / 1e6:.0f} MB; '
          'biggest: ' + ', '.join(f'{p} {b / 1e6:.0f} MB' for p, b in big))


if __name__ == '__main__':
    {'sync': sync, 'show': show}[sys.argv[1]]()
