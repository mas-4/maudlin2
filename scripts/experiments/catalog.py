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
            'S': 'stories and sagas', 'U': 'the machine alone, without curation', 'ASR': 'transcription'}
# code: (name, script, status, data, result)
REGISTRY = {
    'A1': ('Our pipeline on 1,518 ATU-labelled folktales', 'a1_folktales.py', 'answered',
           'a1_folktales.json; archives/trilogy', 'right type in the shortlist ~9 in 10, picked 4 in 5, judge AUC 0.93-0.95'),
    'A2': ('The 1896 newspapers: does filing hold up off-distribution; controls', 'a2_newspapers.py', 'running',
           f'{ARCHIVES} (american_stories_1896: 413,186 articles; claims, filings); a2_newspapers.json (resume state)', ''),
    'A3': ('Viral Texts: do reprints of one piece file alike?', 'a3_viral_texts.py', 'running',
           f'{ARCHIVES} (viral_texts_1836_1861: 49,999 reprints); a3_viral_texts.json (resume state)', ''),
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
    'E13': ('A fuller telling for finding a claim\'s motifs (from A1)', 'e13_richer_telling.py', 'running',
            'e13_richer_telling.json', ''),
    'P2': ('The Oct 10 praxis: the judge\'s question and the naming rules', 'p2_praxis_oct10.py', 'in production',
           'p2_praxis_oct10.json', 'naming rules live Oct 10'),
    'P2b': ('The naming rules without a leading "The"', 'p2b_no_the.py', 'your call', '', 'house style kept'),
    'S1': ('A new event or the same one updated?', 's1_story_splits.py', 'answered', 's1_story_splits.json; s1_doc_rows.json',
           'Gemma agrees 78%, Nimble 60%'),
    'S2': ('Re-sorting a saga\'s headlines into parts', 's2_saga_resort.py', 'not yet', 's2_*.json',
           'three dry runs: k-means plus merging lumps or splits wrongly'),
    'S3': ('What makes headlines one story: TF-IDF, embeddings or hybrids', 's3_story_similarity.py', 'running',
           's3_story_similarity.json; s3_day.json', ''),
    'S4': ('Seams in stories: embeddings, then TF-IDF cuts', 's4_story_seams.py', 'running', 's4_story_seams.json', ''),
    'U1b': ("Golem II: the Golem's broad motifs split by Gemma into the tellings inside", 'u1_uncurated.py split',
            'planned', 'u1_uncurated.json (split); archives/u1', ''),
    'U1': ('The machine alone: our filing from an empty index', 'u1_uncurated.py', 'running',
           f'{ARCHIVES} (runs U1:*); archives/u1 (sandboxes)', ''),
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
        ('J1', 'A jury of models for the judge', 'in production', 'Nimble 9B judges as well as Gemma 26B, faster'),
        ('J2', 'The judge as the casebook reasons', 'in production', 'the element won: AUC 0.54 to 0.79'),
        ('C1', 'Small models first, Gemma only when unsure', 'not kept', 'Gemma alone picks with the fewest wrong'),
        ('R1', 'A bigger reranker (4B)', 'not kept', 'not worth it'),
        ('W1', "Writing claims with rules from the person's corrections", 'unproven', 'Gemma closer than Qwen; rules unproven'),
        ('G1', 'Genre descriptions from the praxis', 'in production', 'genre calls right 53% to 64-67%'),
        ('G2', 'Group descriptions for the drafter', 'not kept', 'no help'),
        ('M1', 'Gemma 26B or Qwen3 30B for the match question', 'in production', 'Gemma; the 30B retired'),
        ('P1', 'Nimble scoring the proposals', 'in production', 'ranking AUC 0.772 against 0.755')]:
    REGISTRY.setdefault(code, (name, '', status, '', result))
# Codenames (Oct 11, the person, on a bike ride: "i hate your experiment codes you should give them codenames like figures
# from folklore"): code -> (figure, why it fits). The code stays the scripts' and logs' key; people say the figure
CODENAMES = {
    'A1': ('Scheherazade', 'a thousand and one tales, told again'),
    'A2': ('Rip Van Winkle', 'wakes in 1896 and tells what he finds'),
    'A3': ('Echo', 'one voice, repeated from paper to paper'),
    'A4': ('Cassandra', 'speeches warning of the enemy within'),
    'A5': ('Fama', "Virgil's Rumour, who runs through the early modern news"),
    'A6': ('Argus', 'the many-eyed watchman, set on known conspiracies'),
    'A7': ('Nestor', 'the old counsellor of long speeches, 140 years of them'),
    'A8': ('the Sphinx', 'riddles of a cabal, set beside 1896'),
    'A9': ('Rashomon', 'one claim, told back by many checkers'),
    'U1': ('the Golem', 'made by us, left to work alone'),
    'U1b': ("the Sorcerer's Apprentice", 'each broom split in two, and in two again'),
    'S1': ('Janus', 'looks back and forward: a new event, or the same one?'),
    'S2': ('Penelope', 'weaves the saga and unpicks it again'),
    'S3': ('Rumpelstiltskin', 'the power is in the exact words'),
    'S4': ('Atropos', 'the Fate who cuts the thread where it frays'),
    'E12': ('Jack', 'seeds, and whether they grow'),
    'E13': ('Anansi', 'the spider who owns every story, told in full'),
    'D1': ('Cinderella', 'the slipper must fit: the must-have element'),
    'D2': ('Bluebeard', "the rooms of past removals"),
    'D3': ('the Hydra', 'many heads asked at once'),
    'D4': ('Proteus', 'motifs that shift shape and drift'),
    'D5': ('Punch and Judy', 'the stock roles: who does what to whom'),
    'P1': ('Puck', 'the mischief-maker who proposes'),
    'P2': ('Adam', 'who named every creature'),
    'P2b': ('Nobody', "Odysseus's name for himself: a name without 'The'"),
    'E0.1': ('the Oracle', 'a yes or no from on high'),
    'E0.2': ('Sisyphus', 'rolls the ranking uphill again'),
    'E0.5': ('the Bremen Town Musicians', 'a band of finders, stronger together'),
    'E0.6': ('Athena', 'the wise judge of which filings to keep'),
    'E1': ('Lethe', "the river of forgetting: the day's news washed out"),
    'E2': ('Morpheus', 'dreamed-up instances'),
    'E3': ('the Pleiades', 'stars that travel together'),
    'E4': ('the Three Wise Men', 'a jury of readers'),
    'E5': ('Arachne', 'scores spread along the web of links'),
    'E6': ('Ariadne', 'the thread through the check queue'),
    'E7': ('Matryoshka', 'a claim read layer by layer'),
    'E8': ('Narcissus', 'shown its nearest likeness'),
    'E9': ('Pygmalion', "shaped to the person's taste"),
    'E11': ('Babel', 'every embedding model, every tongue'),
    'J1': ('the Norns', 'three judges of fate'),
    'J2': ('Solomon', 'judges as the casebook reasons'),
    'C1': ('Goldilocks', 'small, middling and big models, in turn'),
    'R1': ('Goliath', 'the bigger reranker, not worth it'),
    'W1': ('the Brothers Grimm', 'rewording the tales'),
    'G1': ('Mother Goose', 'what each kind of tale is'),
    'G2': ('Noah', 'sorting into groups'),
    'M1': ('the Changeling', 'one model swapped for another'),
}
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
