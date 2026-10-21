"""Filing claims in the motif index (split from motif_index.py on Oct 21, Fable's architecture review): naming a claim's
shape against the closest motifs, matching a new name to the motifs we have, the shortlist, file_claims and the
nightly run that feeds it, the story a filing was told about, and the index's metrics over time. Reached as before
through motif_index (mi.file_claims, mi.nightly); the index itself is read and written through motif_index's store."""
import json
from collections import Counter, defaultdict
import os
import re
from datetime import datetime as dt

import numpy as np

from app.analysis import llm, trace
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json
from app.analysis import motif_index as mi

logger = get_logger(__name__)


# Whether a newly named shape is one the index has already (match()): Gemma 4 26B since Oct 10, the model the rest of
# the filing uses, so it no longer trades places on the card with Qwen3 30B for this one question. On the person's 33
# merges and 44 "not the same" verdicts it found 20 of the merges against the 30B's 18, joined 4 not-same pairs as the
# 30B did, and took 12.9 s a call against 17.6 (M1 in docs/filing-experiments.md)
MODEL = 'gemma4:26b'
CANDIDATES = 5
# Entries less alike than this aren't offered. Oct 5, with the 8B judging: good merges' phrases were 0.77-0.86 alike,
# most bad ones 0.71-0.75 (0.6 let vague early entries snowball). Oct 6, the 30B judging against a person's 31 merges
# and 45 "not the same" verdicts: at 0.7 the merged motif reached it for 7 merges (it found all 7) and 1 of 11
# not-same pairs was joined; at 0.6, 14 found of 20 reaching it, 2 of 26 joined: twice the duplicates caught, at the
# same rate of wrong joins (docs/models.md)
MATCH_FLOOR = 0.6
MAX_NEW = 200  # claims filed a run, at most
# Naming sees the index first (Oct 5): named one claim at a time without it, 223 of 259 motifs held one claim
# ('Smug smirk', 'Houthi territorial expansion') and the same name was coined three times as separate entries
SHOWN = 8  # existing motifs shown when filing a claim, the closest to it (the user's motif was among the closest 8 for
# 77% of their settled claims, Oct 5)
# Filing judges the closest motifs side by side (Oct 6, after a bake-off on 60 of the user's settled claims: the old
# pick-or-name call to the 30B chose their motif for 37%; side by side, Gemma 4 26B for 57% with 54% of its picks
# theirs, at 2.4 s a claim; methods log and docs/models.md)
JUDGE_MODEL = 'gemma4:26b'
SHOWN_FLOOR = 0.45  # ...if at least this alike

# How a new motif is named (docs/motif-praxis.md, "Naming a proposed motif", Oct 10): the person renamed or rejected
# every name the model gave in the old style ("three to seven words, terse like a folklorist's label"). With these
# rules (P2, Oct 10) abstract labels went from 51% of names to 10% and five words to three, and the person judged the
# names "way, way better"; on 101 motifs none copied an example. Not told about "The" (the praxis keeps it for
# Archetypes): told so, the model began 80% of names with it, every genre alike, up from 62% (P2b, Oct 10). Filled
# into NAME_PROMPT, NEW_PROMPT and the proposer's NEW_MOTIF_PROMPT
NAME_RULES = """in one to five words that make sense alone on a chip:
- say it the way people say it: an idiom, a catchphrase or the tellers' own words (They're pouring in!, Shocked, \
shocked!, I could shoot someone on Fifth Avenue, The hospitals will close, Wealth without well-being, Gaslit);
- or a well-known story whose plot is the shape, when the reference lands (Camp of the Saints, Five O'Clock Follies, \
Hoist by his own petard, Sholay, Human centipede, No second acts, Bread and circuses); not Latin for its own sake;
- no abstract nominalizations ("X of Y via Z"), no academic labels, no topic labels ("Trump's influence on \
candidates" became Dead weight president);
- name the shape, not the case: general enough for the next story (Driven off the land, not the settlers); a kind of \
person is an Archetype and sounds like one (RINO, Champagne socialist, Culture warrior, Equivocator)"""
NAME_PROMPT = """A claim people are telling or arguing over:
{claim}

Name the recurring rumor or narrative shapes it is an instance of: none to three, each named {rules}; without \
hedges such as "a claim that" or "is accused of": a shape that would fit the same kind of story told about \
other people, places or years. A story often \
carries more than one shape (who is blamed, what is feared, what is hoped); give each separately, the main one \
first, and don't pad: most claims have one or two. No names of people, places, organizations or dates. A framing \
people contest can name both sides of the dispute in one label. Judge the shapes as the tellers tell the story, not whether it's true. \
Check each name: would it still fit if the people and the event were different? If it only describes this one \
event, make it more general; if it would fit almost any story, make it more specific. A claim that only reports an \
event or states a fact, with no story told around it, has none: give an empty list rather than force one."""
NAME_SCHEMA = {"type": "object", "properties": {"motifs": {"type": "array", "minItems": 0, "maxItems": 3,
                                                          "items": {"type": "string", "maxLength": 60}}},
               "required": ["motifs"]}
REUSE_PROMPT = """Today is {today}. A claim people are telling or arguing over:
{claim}

Motifs in our index of recurring rumor and narrative shapes, each with some of the claims filed under it:
{options}

Which of these motifs is this claim clearly another instance of: the same kind of story as the claims filed under it, \
told about other people, places or years? Judge by what a motif's claims have in common, not by details only some of \
them share; a shared topic, person or place alone isn't enough. Most claims fit one or two; if none fits clearly, \
give none.

reason: a sentence or two
fits: the numbers of the motifs it clearly fits (none to three)"""

# Asked only when no motif fits: one question at a time (offering a new name in the same call as the judging made the
# judge pick the user's motif for 50% of their claims instead of 57%, Oct 6)
NEW_PROMPT = """A claim people are telling or arguing over:
{claim}

None of the motifs in our index of recurring rumor and narrative shapes fits it; the closest were: {closest}.

Does the claim tell a recurring story, the kind told again about other people, places or years? If it does, name it \
as a new motif, {rules}; no names of people, places, organizations or dates. If it only reports an event or states a fact, with no story told around it, \
give no name: don't force one.

reason: a sentence
new: the new motif's name, or nothing"""

MATCH_PROMPT = """A rumor shape: {phrase}
(from the claim: {claim})

Motifs already in our index, each with claims filed under it:
{options}

Is it the same motif as one of these: the same specific recurring shape, even if told about different people or \
events? A similar theme or a shared subject isn't enough: the claims should be the same kind of story. Give its \
number, or "new" if none of them is the same shape."""


MAX_WORDS = 7  # a longer 'name' is a sentence, usually the claim itself (an LAX kidnapping claim became one, Oct 5)


def match(index: dict, phrase: str, claim: str) -> str | None:
    """The existing entry this shape is the same motif as, or None: the closest few by meaning, then the model's
    forced choice with "new" on offer."""
    from app.narratives import embed
    entries = [e for e in mi.live(index) if mi.key(claim) not in e.get('not_claims', [])]  # a person said it isn't
    if not entries:
        return None
    # Each entry by its name and its claims' phrases together, so a curated name still matches its kind
    texts = [mi.described(e) + '. ' + '; '.join(e.get('phrases', [])[:5]) for e in entries]
    v = embed([phrase] + texts)
    sims = v[1:] @ v[0]
    top = [int(i) for i in np.argsort(-sims)[:CANDIDATES] if sims[i] >= MATCH_FLOOR]
    if not top:
        return None
    options = '\n'.join(f'{n}. {mi.described(entries[i])} (e.g. ' + '; '.join(
        f'"{x["claim"][:110]}"' for x in entries[i]['claims'][-2:]) + ')' for n, i in enumerate(top, 1))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string", "maxLength": 1000},  # cut off mid-reason, the 30B answers no (as with sagas)
        "pick": {"type": "string", "enum": [str(n) for n in range(1, len(top) + 1)] + ['new']}},
        "required": ["reason", "pick"]}
    answer = llm.complete_json(MATCH_PROMPT.format(phrase=phrase, claim=claim, options=options), schema,
                               max_tokens=500, model=MODEL)
    return entries[top[int(answer['pick']) - 1]]['id'] if answer and answer['pick'] != 'new' else None


def closest(index: dict, claim: str) -> list[dict]:
    """The existing entries most like a claim, by meaning (its name, phrases and claims together), for naming it."""
    from app.narratives import embed
    entries = [e for e in mi.live(index) if mi.key(claim) not in e.get('not_claims', [])]  # a person said it isn't
    if not entries:
        return []
    texts = [mi.described(e) + '. ' + '; '.join(e.get('phrases', [])[:5]) + '. ' + '; '.join(x['claim'][:120] for x in e['claims'][-2:])
             for e in entries]
    v = embed([claim] + texts)
    sims = v[1:] @ v[0]
    return [entries[int(i)] for i in np.argsort(-sims)[:SHOWN] if sims[i] >= SHOWN_FLOOR]


def name_claim(claim: str, shown: list[dict]) -> dict | None:
    """{'existing': [entries the judge filed it under], 'new': [a name for a shape none of them covers]}, or None.
    The closest motifs are judged side by side, each by its name, scope note and three of its claims; the picks come
    back as numbers (Qwen3.5 under Ollama returned an empty list of fixed strings, Oct 5)."""
    from datetime import datetime
    if not shown:
        named = llm.complete_json(NAME_PROMPT.format(claim=claim, rules=NAME_RULES), NAME_SCHEMA, max_tokens=300, model=JUDGE_MODEL)
        return named and {'existing': [], 'new': [m for m in map(mi.clean, named.get('motifs', [])) if fits_name(m)][:1]}
    options = '\n'.join(f'{n}. {mi.described(e)}{mi.not_this(e)}\n' + '\n'.join(f'   - {c["claim"][:160]}' for c in e['claims'][-3:])
                        for n, e in enumerate(shown, 1))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string", "maxLength": 1000},
        "fits": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": len(shown)}}},
        "required": ["reason", "fits"]}
    answer = llm.complete_json(REUSE_PROMPT.format(today=datetime.now().strftime('%B %-d, %Y'), claim=claim,
                                                   options=options), schema, max_tokens=900, model=JUDGE_MODEL)
    if not answer:
        return None
    existing = [shown[n - 1] for n in dict.fromkeys(answer.get('fits', [])) if isinstance(n, int) and 1 <= n <= len(shown)][:3]
    if existing:
        return {'existing': existing, 'new': [], 'reason': answer.get('reason')}
    schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                               "new": {"type": "array", "maxItems": 1, "items": {"type": "string", "maxLength": 60}}},
              "required": ["reason", "new"]}
    named = llm.complete_json(NEW_PROMPT.format(claim=claim, rules=NAME_RULES, closest='; '.join(e['name'] for e in shown[:5])), schema,
                              max_tokens=500, model=JUDGE_MODEL)
    if named is None:
        return None
    return {'existing': [], 'new': [m for m in map(mi.clean, named.get('new', [])) if fits_name(m)],
            'reason': answer.get('reason'), 'new_reason': named.get('reason')}


def fits_name(name: str) -> bool:
    return bool(name) and len(name.split()) <= MAX_WORDS


def same_name(index: dict, phrase: str) -> str | None:
    """An entry already called this (case and punctuation aside): one name, one motif"""
    norm = lambda t: re.sub(r'[^a-z0-9 ]', ' ', t.lower()).split()  # noqa: E731
    return next((e['id'] for e in mi.live(index) if norm(e['name']) == norm(phrase)), None)


SHORTLIST_LOG = os.path.join(Config.data, 'motifs', 'shortlist_log.jsonl')


def log_shortlist(index: dict, c: dict, shown: list[dict], named: dict):
    """What a new claim was shown and what the filing model made of it, before anyone judged it (Oct 12, Prometheus,
    from Fable's review: the shortlist's held-out recall is measured on filings it already found; this is the forward
    record, scored weekly against the person's final word). 'next' is the next motif number then, so a motif the
    person makes later is told from one that existed but wasn't shown. Never stops a filing"""
    try:
        with open(SHORTLIST_LOG, 'a') as f:
            f.write(json.dumps({'at': dt.now().isoformat(timespec='seconds'), 'key': mi.key(c['claim']), 'claim': c['claim'],
                                'source': c.get('source', ''), 'next': index['next'],
                                'shown': [e['id'] for e in shown], 'seeds': [e['id'] for e in shown if not e['claims']],
                                'picked': [e['id'] for e in named['existing']], 'new': named['new']}) + '\n')
    except (OSError, KeyError, TypeError) as e:
        logger.warning("Shortlist log: %s", e)
LINK_FIELDS = ('split_from',)  # a child claim's telling, the claim it was split from (claim_organizer.apply_split)


def record(c: dict, today: str) -> dict:
    """A filing's claim record, with the story the claim was told about when its source ties it to one (see
    story_motifs), and the telling it was split from, if it was"""
    return {'claim': c['claim'], 'source': c.get('source', ''), 'ref': c.get('ref', ''), 'side': c.get('side'),
            'date': c.get('date') or today, **{f: c[f] for f in mi.STORY_FIELDS + LINK_FIELDS if c.get(f) is not None}}


class Shortlister:
    """The motifs filing shows the judge for a claim: the learned shortlist (motif_retriever: every signal weighed, when
    it tests better), the plain weights' without it, the closest 8 without either. Each claim's shape and layers are
    asked first for all the claims at once, llm.PARALLEL at a time, and kept (save()). Shared by file_claims and the
    watch list's refiling (watch_list.py)"""

    def __init__(self, index: dict, claims: list[str], budget: float | None = None):
        from app.analysis import motif_retriever
        self.weights, self.vectors = motif_retriever.weights(), motif_retriever.Vectors()
        self.learned = motif_retriever.learned() if self.weights else None
        self.sig = None
        if self.learned:
            try:
                from app.analysis import motif_signals
                self.sig = motif_signals.Signals(index, self.vectors)
                self.sig.prepare(claims, budget=budget)
            except Exception as e:  # noqa: BLE001 - each claim asks its own
                logger.warning("Motif filing: preparing the shortlists failed (%s)", e)
                self.sig = None

    def __call__(self, index: dict, claim: str) -> list[dict]:
        from app.analysis import motif_retriever
        if self.weights:
            try:
                if self.learned:
                    ids = [e['id'] for e in mi.live(index) if e['claims']]
                    if self.sig is None or [e['id'] for e in self.sig.entries] != ids:  # a motif made or gone meanwhile
                        from app.analysis import motif_signals
                        self.sig = motif_signals.Signals(index, self.vectors)
                    return motif_retriever.learned_shortlist(index, claim, self.sig, self.weights, self.learned)
                return motif_retriever.shortlist(index, claim, self.vectors, self.weights)
            except Exception as e:  # noqa: BLE001 - the closest 8 will do
                logger.warning("Motif retriever failed (%s); the closest motifs instead", e)
        return closest(index, claim)

    def save(self):
        if self.sig is not None:
            self.sig.save()


def file_claims(claims: list[dict], limit: int = MAX_NEW, budget: float | None = None) -> dict:
    """File each claim ({'claim', 'source': 'narrative' or a fact-checker's name, 'ref', 'side', and 'story' and
    'story_tie' when known}) under a motif, creating entries as needed. Claims already filed are left where they are.
    Returns the index."""
    index = mi.load()
    todo = [c for c in claims if c.get('claim') and mi.key(c['claim']) not in index['claims']][:limit]
    if not todo or llm.backend() is None:
        return index
    today = dt.now().strftime('%Y-%m-%d')
    import time
    started = time.time()
    outcomes = Counter()  # for the metrics: each claim matched to motifs already there, given a new one, or none
    lister = Shortlister(index, [c['claim'] for c in todo], budget=None if budget is None else budget / 2)
    for n, c in enumerate(todo):
        if budget is not None and time.time() - started > budget:
            break  # the next run picks up where this one stopped
        if n and n % 25 == 0:  # progress a watcher can read (the experiments' queue: a step that shows none is stuck)
            logger.info("Motif filing: %d/%d claims", n, len(todo))
        # One claim at a time on a fresh read of the index, saved as it goes: a run cut short keeps what it filed, and
        # an edit made in the checker meanwhile isn't lost. The models (the shortlist, the naming, matching a new name)
        # are asked on an unlocked read; only the change takes the lock, on the index as it is then (Oct 21: held
        # through the models' seconds for each claim, every click in the checker waited while a run filed)
        index = mi.load()
        if mi.key(c['claim']) in index['claims']:
            continue
        shown = lister(index, c['claim'])
        trace.shortlisted(c, shown, lister, next_motif=index['next'])  # the 🧠 Live page's view of it (app/analysis/trace.py)
        named = name_claim(c['claim'], shown)
        if not named:
            continue
        coined = [(phrase, same_name(index, phrase) or match(index, phrase, c['claim']))
                  for phrase in named['new'][:max(0, 3 - len(named['existing']))]]
        with mi.locked():
            index = mi.load()
            if mi.key(c['claim']) in index['claims']:  # filed meanwhile (a person, or another run)
                continue
            log_shortlist(index, c, shown, named)
            filed = []
            for e in named['existing']:
                eid = mi.resolve(index, e['id'])  # merged meanwhile: where it went
                entry = index['entries'].get(eid)
                if entry is None or eid in filed:  # deleted meanwhile
                    continue
                entry['claims'].append(record(c, today))
                entry['last_seen'] = max(entry.get('last_seen') or '', c.get('date') or today)
                filed.append(eid)
            for phrase, eid in coined:
                eid = same_name(index, phrase) or (mi.resolve(index, eid) if eid else None)  # one named so meanwhile
                if eid is not None and eid not in index['entries']:
                    eid = None
                if eid in filed:
                    continue
                if eid is None:
                    eid = f"M{index['next']:03d}"
                    index['next'] += 1
                    index['entries'][eid] = {'id': eid, 'name': phrase, 'curated': False, 'first_seen': today,
                                             'claims': [], 'phrases': []}
                entry = index['entries'][eid]
                entry['claims'].append(record(c, today))
                entry['phrases'] = (entry.get('phrases', []) + [phrase])[-20:]
                entry['last_seen'] = max(entry.get('last_seen') or '', c.get('date') or today)
                filed.append(eid)
            index['claims'][mi.key(c['claim'])] = filed
            new_ids = [eid for eid in filed if index['entries'][eid].get('first_seen') == today and len(index['entries'][eid]['claims']) == 1]
            trace.picked(c['claim'], named, filed, new_ids)
            made = len(new_ids)
            outcomes['none' if not filed else 'new' if made else 'matched'] += 1
            mi.save(index)
    lister.save()  # the new claims' shapes and layers, asked once
    if outcomes:
        os.makedirs(os.path.dirname(FILING_LOG), exist_ok=True)
        with open(FILING_LOG, 'a') as f:
            f.write(json.dumps({'at': dt.now().isoformat(timespec='seconds'), **outcomes}) + '\n')
    logger.info("Motif index: filed %d claims (%s); %d motifs", len(todo), dict(outcomes), len(mi.live(index)))
    return index


# The index's shape over time (for the workbench's stats): a snapshot a day, the latest of the day kept; and each
# filing run's outcomes. What came before Oct 6 is rebuilt where it can be (new motifs from first_seen, a person's
# work from the curation log and the motif checks)
METRICS = os.path.join(Config.data, 'motifs', 'metrics.json')
FILING_LOG = os.path.join(Config.data, 'motifs', 'filing_log.jsonl')


def metrics(index: dict | None = None) -> dict:
    """How the catalog looks now: its size, how much of it is single claims, how much is organized (kinds, genres,
    groups), how much a person has been through (done, notes, checks)"""
    index = index if index is not None else mi.load()
    es = mi.live(index)
    n = max(1, len(es))
    kids = {p for e in es for p in mi.parents_of(e)}
    sizes = [len(e['claims']) for e in es]
    filings = sum(sizes)
    share = lambda k: round(100 * k / n, 1)  # noqa: E731
    return {
        'motifs': len(es), 'claims': sum(1 for ids in index['claims'].values() if ids), 'filings': filings,
        'no_motif': sum(1 for ids in index['claims'].values() if not ids),
        'per_motif': round(filings / n, 2),
        'singles': share(sum(1 for k in sizes if k == 1)), 'two_plus': share(sum(1 for k in sizes if k >= 2)),
        'in_tree': share(sum(1 for e in es if mi.parents_of(e) or e['id'] in kids)),
        'with_genre': share(sum(1 for e in es if (e.get('facets') or {}).get('genre'))),
        'in_group': share(sum(1 for e in es if mi.groups_of(e))),
        'done': share(sum(1 for e in es if 'done' in e)),
        'your_notes': share(sum(1 for e in es if e.get('note') and e.get('note_by') not in mi.DRAFTS)),
        'checked': round(100 * sum(1 for e in es for c in e['claims'] if c.get('checked')) / max(1, filings), 1),
        'variants': sum(len(c.get('variants', [])) for e in es for c in e['claims']),
        **sure_share(es),
    }


def sure_share(es: list[dict]) -> dict:
    """The person's workload (Oct 11, the person: "are we going to be able to see if/when that 85% right number climbs
    over time?"): of the day's filings in their motifs, how many the confidence model puts past its sure line, as the
    day's snapshot keeps it (the model of that day). As it climbs while the sure ones stay as right, there's less to
    look at and correct"""
    from app.analysis import filing_confidence as fc
    sure_at = next((r['sure_at'] for r in reversed(fc.history()) if r.get('model') == 'confidence' and r.get('sure_at')), None)
    today = dt.now().strftime('%Y-%m-%d')
    fits = [c['fit'] for e in es if 'done' in e for c in e['claims'] if c.get('fit') is not None and c.get('date', '')[:10] == today]
    if not sure_at or not fits:
        return {}
    return {'filed_today': len(fits), 'sure_share': round(100 * sum(f >= sure_at for f in fits) / len(fits), 1)}


def snapshot_metrics():
    """Today's metrics into the history (the latest of the day wins)"""
    from app.utils.store import read_json
    history = read_json(METRICS, {})
    history[dt.now().strftime('%Y-%m-%d')] = metrics()
    write_json(METRICS, history)


def metrics_history() -> dict:
    """Per day: the snapshots, new motifs (from first_seen; merged ones count, they were made), the filing runs'
    outcomes, and a person's work (curation actions, motif checks)"""
    from app.utils.store import read_json
    index = mi.load()
    days = defaultdict(lambda: defaultdict(int))
    for e in index['entries'].values():
        if e.get('first_seen'):
            days[e['first_seen'][:10]]['new_motifs'] += 1
    try:
        with open(FILING_LOG) as f:
            for line in f:
                r = json.loads(line)
                for k in ('matched', 'new', 'none'):
                    days[r['at'][:10]]['filed_' + k] += r.get(k, 0)
    except OSError:
        pass
    folder = os.path.join(Config.data, 'validation')
    for name, field in (('curation_log.jsonl', 'actions'), ('motif_verdicts.jsonl', 'checks')):
        try:
            with open(os.path.join(folder, name)) as f:
                for line in f:
                    r = json.loads(line)
                    day = (r.get('at') or '')[:10]
                    if not day:
                        continue
                    if field == 'checks':
                        days[day]['checks_' + ('yes' if r.get('answer') == 'yes' else 'no' if r.get('answer') == 'no' else 'unsure')] += 1
                    elif (r.get('action') or {}).get('action') not in (None, 'undo'):
                        days[day]['actions'] += 1
        except (OSError, ValueError):
            pass
    snaps = read_json(METRICS, {})
    out = []
    for day in sorted(set(days) | set(snaps)):
        if day < '2026-10-01':
            continue
        out.append({'day': day, **days.get(day, {}), **({'shape': snaps[day]} if day in snaps else {})})
    return {'now': metrics(index), 'days': out, 'models': model_days()}


def model_days() -> list[dict]:
    """The models' held-out tests (filing_confidence.HISTORY), the day's last of each model: how good the machine is,
    measured on the person's checks it didn't learn from, so it doesn't move with what they choose to check"""
    from app.analysis import filing_confidence as fc
    days = defaultdict(dict)
    for r in fc.history():
        d = days[r['at'][:10]]
        if r.get('model') == 'confidence':
            d.update({k: r[k] for k in ('auc', 'right_when_sure', 'sure_at', 'decisions') if r.get(k) is not None})
        elif r.get('model') == 'shortlist':
            d.update({k: r[k] for k in ('top12', 'plain_top12') if r.get(k) is not None})
    return [{'day': day, **d} for day, d in sorted(days.items())]


def nightly(budget: float | None = None):
    """File the latest report's narratives and the last 30 days' fact-checked claims not filed yet, for at most
    `budget` seconds."""
    from app.analysis import factchecks
    from app.narratives import latest_report
    claims = []
    from app.narratives import NOT_STORIES, withheld
    report = latest_report() or {}
    pulled = withheld()
    index = mi.load()  # for corrected summaries
    for g in report.get('found', []):
        lab = g.get('label') or {}
        if lab.get('retold') and lab.get('narrative') and lab['narrative'] not in pulled and fits(lab):
            claims.append({'claim': mi.corrected(lab['narrative'], index), 'source': 'narrative', 'ref': report.get('made', ''),
                           'side': g.get('shared_side'), 'date': (report.get('made') or '')[:10], **mi.story_of_group(g)})
    labels = factchecks.load_labels()
    checked = factchecks.stories_of()
    for item in factchecks._items(factchecks.LABEL_DAYS):
        lab = labels.get(item['url']) or {}
        if lab.get('claim') and lab.get('genre') not in NOT_STORIES:  # a roundup or explainer checks no rumor
            claims.append({'claim': mi.corrected(lab['claim'], index), 'source': item['source'], 'ref': item['url'],
                           'date': item['published'][:10],
                           **({'story': checked[item['url']]} if item['url'] in checked else {})})
    # The Focus Group's and the shows' claims carry no story: an episode covers several, and nothing cheap says which
    # one a claim is about
    from app.analysis import focus_group  # what voters say in focus groups: a source of its own
    claims += [{**c, 'claim': mi.corrected(c['claim'], index)} for c in focus_group.claims()]
    from app.analysis import show_claims  # what's retold across the shows we transcribe
    claims += [{**c, 'claim': mi.corrected(c['claim'], index)} for c in show_claims.claims()]
    import time
    started = time.time()
    try:  # the learned shortlist, retrained when a day old
        from app.analysis import motif_retriever
        motif_retriever.learned(retrain=True)
    except Exception as e:  # noqa: BLE001 - filing goes on with the plain weights
        logger.warning("Motif shortlist: %s", e)
    index = file_claims(claims, budget=None if budget is None else max(60, budget - (time.time() - started)))
    try:
        snapshot_metrics()
    except Exception as e:  # noqa: BLE001 - the stats are extra
        logger.warning("Motif metrics: %s", e)
    try:  # how many separate occasions each motif is told on (attested or placed)
        from app.analysis import motif_told
        motif_told.refresh()
    except Exception as e:  # noqa: BLE001 - the count is extra; the next run tries again
        logger.warning("Motif occasions: %s", e)
    # New motifs get the model's draft of a scope note (shown on the board to keep or edit; used in matching at once)
    mi.gloss_missing(budget=None if budget is None else max(30, budget - (time.time() - started)))
    try:
        mi.draft_missing(budget=None if budget is None else max(60, budget - (time.time() - started)))
    except Exception as e:  # noqa: BLE001 - drafts are extra; the next run tries again
        logger.warning("Motif drafts: %s", e)
    return index


def fits(label: dict) -> bool:
    """Whether a folklore group's claim belongs in the index. Political ones do, news included: news is powerful when it
    confirms a story people already tell (a Russian lab worker's plague death, told as a bioweapon). Other folklore
    does when it has a subject (contamination scares, legends), but not a shared topic, a sports pick or a game
    result (a Valkyries semifinal 'prophecy' got 'Valkyries to defeat Aces', Oct 5)."""
    from app.narratives import NOT_STORIES
    if label.get('genre') == 'none: a shared topic, not a retold narrative':
        return False
    if label.get('politics'):
        return True
    return label.get('genre') not in NOT_STORIES and label.get('family') not in (None, '', 'none')


def report_stories(index: dict) -> dict[str, dict[str, dict]]:
    """Each saved narrative report's story ties, by the report's time (a narrative filing's ref): {made: {claim, in the
    model's words and as corrected since: story fields}}"""
    import glob
    from app import narratives
    out = {}
    reports = [read_json(path, {}) for path in glob.glob(os.path.join(narratives.FOLDER, 'report-*.json'))]
    try:  # a group the model left untied takes the story its posts link to (narratives.linked_story, Oct 12)
        known = narratives.articles(sorted({u for r in reports for g in r.get('found', []) for u, _ in g.get('shared') or []}))
    except Exception as e:  # noqa: BLE001 - the model's ties alone
        logger.warning("Motif index: shared links unread (%s)", e)
        known = {}
    for report in reports:
        ties = out.setdefault(report.get('made', ''), {})
        for g in report.get('found', []):
            if not g.get('story'):
                g = {**g, 'story': narratives.linked_story(
                    {'articles': [{**known[u], 'shares': n} for u, n in g.get('shared') or [] if u in known]})}
            lab, st = g.get('label') or {}, mi.story_of_group(g)
            if lab.get('narrative') and st:
                ties[lab['narrative']] = ties[mi.corrected(lab['narrative'], index)] = st
    return out


@mi.exclusive
def backfill_stories() -> dict:
    """Story ids for the filings made before filings kept them (Oct 12): a narrative's from the report it came in (its
    ref is the report's time), a fact-check's from factchecks.stories_of(). Only adds: a filing's story is never
    changed. How many records got one, by kind"""
    from app.analysis import factchecks
    index = mi.load()
    reports, checked = report_stories(index), factchecks.stories_of()
    done = Counter()
    for e in index['entries'].values():
        for c in e.get('claims', []):
            if c.get('story') is not None:
                continue
            if c.get('source') == 'narrative':
                st = reports.get(c.get('ref', ''), {}).get(c['claim'])
            else:
                st = {'story': checked[c['ref']]} if c.get('ref') in checked else None
            if st:
                c.update(st)
                done['narrative' if c.get('source') == 'narrative' else 'fact-check'] += 1
    if done:
        mi.save(index)
    logger.info("Motif index: story ids backfilled on %s", dict(done))
    return dict(done)
