"""The experiments' folklore codenames (Oct 11, the person, on a bike ride: "i hate your experiment codes you should
give them codenames like figures from folklore"): code -> (figure, why it fits). The code stays the key in scripts and
logs; people say the figure. On their own, with no imports, so anything can read them cheaply: the catalog
(catalog.py), the desktop widget's lease list (app/desk.py). A lease is named after its figure too ("atropos-judge")."""
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
    'E0.3': ("the Emperor's New Clothes", 'the note alone, and nothing else'),
    'E0.4': ('Hansel and Gretel', 'following the note first, like breadcrumbs'),
    'N4': ('Tom Thumb', 'the smaller Nimble that fits the card'),
    'E0.5': ('the Bremen Town Musicians', 'a band of finders, stronger together'),
    'E0.6': ('Athena', 'the wise judge of which filings to keep'),
    'E1b': ('Chronos', "each claim read in the news of its own time"),
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


def figure_of(lease: str) -> str:
    """A lease's holder as people say it: 'atropos-judge' or 's4-judge' -> 'Atropos · judge'"""
    head, _, rest = lease.partition('-')
    slugs = {f.lower().removeprefix('the ').replace(' ', '').replace("'", ''): f for f, _ in CODENAMES.values()}
    codes = {k.lower(): f for k, (f, _) in CODENAMES.items()}
    fig = codes.get(head.lower()) or slugs.get(head.lower().replace('_', ''))
    if not fig:
        return lease
    fig = fig[0].upper() + fig[1:]
    return f'{fig} · {rest}' if rest else fig
