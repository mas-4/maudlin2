"""The claim organizer (Oct 13; decision 7 of Fable's handoff, Oct 12): a second round for a claim whose posts tell
several things. A claim from posts is one sentence written for a whole paraphrase group, and the group often stitches
tellings together (the Chimera); the filing then picks a motif for each telling and the claim sits in 3+ motifs (32% of
claims from posts, 12 to 17% from other sources). The organizer asks which posts tell which picked motif; if the motifs
land on different posts, it drafts one child claim per telling, each one side's assertion in that side's own voice,
and proposes the split. Approved, the children refile through file_claims and the original stays as the telling.

Triggers, on spread and not on the motif count (the Chimera's one-motif control split as often as its 3+ motif claims,
and honest layering, an archetype, a plot and a value of one telling, also yields 3+ motifs). Each is returned by name,
so how often each fires, and which predict a split, can be counted:

    facing motifs      two picked motifs linked as related with a reason of counter, answers or mirror: one side's
                       move and the other's answer, two side-claims (counter-motifs, Oct 12)
    two of one genre   two picked motifs of one genre: two Plots are two things that happened, not one told in layers
    varied group       the paraphrase group's wording varies more than VARIED (narratives.describe's variety)
    many authors       the group was posted by MANY people or more
    middling scores    every pick's fit is MIDDLING: nothing fits the whole claim well
    also               the person filed the claim in another motif by hand (the board's or checker's 'also'): the
                       filing missed a part of it

A split is a proposal (motif_proposals' store, kind 'split'; when the motifs don't spread, kind 'no_split' with the
reason, status 'none', so the same claim and picks aren't asked again). Nothing is applied until a person approves:
apply_split() takes the parent out of its motifs under its own logged action, 'split', which
filing_confidence._decided never reads as "not this motif" (unfile, reject or move would teach the confidence model
a false lesson); the parent's filings and the children are kept in the index under 'tellings'; the children refile
through file_claims, so they reach the person's queue as new filings, each carrying the parent's source, ref, side,
date and story, and split_from. A person's own split (they write the children) goes the same way, with no proposal.

Post texts are never copied into the proposals: a child keeps its posts' keys, read back from the post store
(app/vernacular.py, kept 30 days) when shown."""
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime as dt

from app.analysis import llm
from app.analysis import motif_index as mi
from app.analysis import motif_proposals as mp
from app.utils import get_logger

logger = get_logger(__name__)

MODEL = 'gemma4:26b'  # the filing model, as the Chimera and the Blind Men read posts
ACTION = 'split'  # the curation log's action for an applied split
POSTS = 40  # of a group's posts read, the most posted first (the Chimera's)
SHOWN = 280  # characters of each post shown
MIN_POSTS = 4  # posts a group needs before it's read for a split
SET_POSTS = 12  # of a telling's posts shown when its child is drafted
VARIED = 0.9  # a group's variety this high: the top quarter of the posts claims' groups on Oct 13 (median 0.867)
MANY = 15  # authors: the top quarter on Oct 13 (median 9)
MIDDLING = (0.3, 0.8)  # every pick's fit inside this: no motif fits the whole claim well
FACING = re.compile(r'\b(counter|answer|mirror)', re.I)  # a related link's reason that makes two motifs face each other
MIN_TOLD = 2  # posts that must tell a motif for it to count as told in the posts
SAME_POSTS = 0.5  # two motifs whose posts overlap this much (of the fewer) are told by the same posts: layers of one
BROAD = 0.8  # a motif told by this share of the posts that tell any is a layer of every telling, not a telling
CHILDREN = 4  # children drafted at most

TELLS_PROMPT = """Posts people wrote, grouped together because they read alike:
{posts}

Motifs (recurring story shapes) the group's claim was filed under:
{motifs}

For each motif, in the order given, list the numbers of the posts that tell it: say it, assume it, or argue from it. \
A post can tell several motifs, or none. Give an empty list for a motif no post tells."""


def tells_schema(n: int) -> dict:
    return {"type": "object", "properties": {"tells": {"type": "array", "minItems": n, "maxItems": n, "items": {
        "type": "array", "items": {"type": "integer"}}}}, "required": ["tells"]}


CHILD_PROMPT = """Posts people wrote, grouped together because they read alike. A reader found they tell {n} different \
things; here are the posts that tell each:

{sets}

For each set, in order, write the claim its posts make: one side's assertion in its tellers' own voice, as they would \
put it, saying what sets it apart from the other sets. Never a sentence about the posts, about an argument or about \
who says what; if a set's posts argue against another set's claim, write their own claim.
{wording}"""


def child_schema(n: int) -> dict:
    return {"type": "object", "properties": {"claims": {"type": "array", "minItems": n, "maxItems": n, "items": {
        "type": "string", "maxLength": 300}}}, "required": ["claims"]}


SIDE_RULE = ("- Each claim is one side's assertion in that side's own voice. Where the posts argue, each side's claim "
             "is its own; never a sentence about the argument (\"Arguments over whether...\" is not a claim).")


def child_rules(index: dict | None = None) -> str:
    """The Brothers Grimm's wording for claims from posts (claim_wording), with decision 6's rule in place of the one
    that words a disagreement as an argument: a child is one side's claim"""
    from app.claim_wording import RULES, SHORT, examples
    rules = '\n'.join(SIDE_RULE if line.startswith('- When the tellers disagree') else line for line in RULES.split('\n'))
    try:
        shown = examples('posts', index)
    except Exception:  # noqa: BLE001 - the rules without examples
        shown = ''
    return '\n' + rules + '\n' + SHORT + shown


# ---------- what's known about a claim ----------

def picks(index: dict, claim: str) -> list[tuple[dict, dict]]:
    """The motifs a claim is filed under, each with the claim's record there: (entry, record), main motif first"""
    k = mi.key(claim)
    out = []
    for e in mi.entries_of(index, claim):
        rec = next((c for c in e['claims'] if mi.key(c['claim']) == k), None)
        if rec is not None:
            out.append((e, rec))
    return out


def alsos(rows: list[dict] | None = None) -> dict[str, list[str]]:
    """Claim key -> the motifs (ids, or a new motif's name) a person filed it in by hand as well as where it was: the
    board's and checker's 'also' and 'also_new', and a new motif made with the claim copied in"""
    if rows is None:
        from app.analysis import filing_confidence as fc
        rows = fc.log_rows()
    out = defaultdict(list)

    def one(a: dict):
        act = a.get('action')
        if act == 'also' and isinstance(a.get('claim'), str) and a.get('target'):
            out[mi.key(a['claim'])].append(a['target'])
        elif act == 'also_new' and isinstance(a.get('claim'), str):
            out[mi.key(a['claim'])].append(a.get('name') or 'new')
        elif act == 'new_with':
            for c in a.get('claims') or []:
                if isinstance(c, dict) and c.get('mode') == 'also' and isinstance(c.get('claim'), str):
                    out[mi.key(c['claim'])].append(a.get('name') or 'new')
        elif act == 'batch':
            for s in a.get('steps') or []:
                if isinstance(s, dict):
                    one(s)
    for r in rows:
        if isinstance(r.get('action'), dict):
            one(r['action'])
    return dict(out)


def report_groups(index: dict | None = None) -> dict[str, list[tuple[str, dict]]]:
    """Claim key (as worded now) -> the paraphrase groups its claim was written for, [(report's time, group)], the
    latest report first: every narrative report read once"""
    import glob
    import os

    from app.narratives import FOLDER
    from app.utils.store import read_json
    index = index if index is not None else mi.load()
    out = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(FOLDER, 'report-*.json')), reverse=True):
        report = read_json(path, {})
        for g in report.get('found', []):
            n = (g.get('label') or {}).get('narrative')
            if n:
                out[mi.key(mi.corrected(n, index))].append((report.get('made', ''), g))
    return dict(out)


def group_of(claim: str, ref: str, groups: dict) -> dict | None:
    """The paraphrase group a claim from posts was written for: the one in its own report (its ref is the report's
    time), else the latest that has it"""
    found = groups.get(mi.key(claim)) or []
    return next((g for made, g in found if made == ref), None) or (found[0][1] if found else None)


def posts_of(keys: list[str], limit: int = POSTS) -> list[dict]:
    """The posts with these keys still kept, each text once with its keys and how many posted it, most first (as
    narratives.posts_of, with the keys)"""
    from app.narratives import normalized
    from app.vernacular import DB
    if not keys:
        return []
    con = sqlite3.connect(DB)
    rows = []
    for start in range(0, len(keys), 500):
        part = keys[start:start + 500]
        rows += con.execute(f'SELECT key, text FROM post WHERE key IN ({",".join("?" * len(part))})', part).fetchall()
    con.close()
    seen = {}
    for k, text in rows:
        p = seen.setdefault(normalized(text), {'text': text, 'keys': [], 'n': 0})
        p['keys'].append(k)
        p['n'] += 1
    return sorted(seen.values(), key=lambda p: -p['n'])[:limit]


def triggers(claim: str, index: dict, group: dict | None = None, also: dict | None = None,
             fits: dict | None = None, motifs: list[str] | None = None) -> dict[str, str]:
    """The triggers that fire for a filed claim, name -> what fired it. `group` is its paraphrase group (variety,
    authors) when it came from posts; `also` the person's hand filings (alsos()); `motifs` other picks than its
    filings, and `fits` motif id -> a score to read instead of each filing's fit (an experiment's own picks)"""
    got = picks(index, claim)
    if motifs is not None:
        recs = {e['id']: rec for e, rec in got}
        got = [(index['entries'][m], recs.get(m, {})) for m in motifs if m in index['entries']]
    fired = {}
    es = [e for e, _ in got]
    for n, a in enumerate(es):
        for b in es[n + 1:]:
            note = mi.related_note(index, a['id'], b['id'])
            if note and FACING.search(note) and 'facing motifs' not in fired:
                fired['facing motifs'] = f"{a['name']} / {b['name']}: {note}"
    by_genre = defaultdict(list)
    for e in es:
        if mi.genre_of(e):
            by_genre[mi.genre_of(e)].append(e['name'])
    two = {g: names for g, names in by_genre.items() if len(names) >= 2}
    if two:
        fired['two of one genre'] = '; '.join(f"{g}: {', '.join(names)}" for g, names in sorted(two.items()))
    if group:
        if (group.get('variety') or 0) >= VARIED:
            fired['varied group'] = f"variety {group['variety']}"
        if (group.get('authors') or 0) >= MANY:
            fired['many authors'] = f"{group['authors']} authors"
    scores = [(fits or {}).get(e['id'], rec.get('fit')) for e, rec in got]
    if scores and all(s is not None and MIDDLING[0] <= s <= MIDDLING[1] for s in scores):
        fired['middling scores'] = ', '.join(f'{s:.2f}' for s in scores)
    hand = (also or {}).get(mi.key(claim))
    if hand:
        names = [index['entries'][t]['name'] if t in index['entries'] else t for t in hand]
        fired['also'] = ', '.join(names)
    return fired


# ---------- reading the posts ----------

def _numbers(xs, n: int) -> list[int]:
    """Post numbers the model gave (from 1), as indexes into the posts, in range and each once"""
    return sorted({int(x) - 1 for x in xs or [] if isinstance(x, (int, float)) and 1 <= int(x) <= n})


def tellings(tells: dict[str, list[int]]) -> tuple[list[dict], list[str]]:
    """The tellings the motifs' posts make: ([{'motifs', 'posts'}], the broad motifs). A motif told by fewer than
    MIN_TOLD posts isn't told; one told by BROAD of the posts that tell any is a layer of every telling; the rest join
    into one telling when their posts overlap SAME_POSTS or more (of the fewer), and stay apart otherwise"""
    told = {m: set(ps) for m, ps in tells.items() if len(set(ps)) >= MIN_TOLD}
    every = set().union(*told.values()) if told else set()
    broad = [m for m, ps in told.items() if len(told) > 1 and len(ps) >= BROAD * len(every)]
    narrow = [m for m in told if m not in broad]
    parent = {m: m for m in narrow}

    def find(m):
        while parent[m] != m:
            m = parent[m]
        return m
    for i, a in enumerate(narrow):
        for b in narrow[i + 1:]:
            if len(told[a] & told[b]) >= SAME_POSTS * min(len(told[a]), len(told[b])):
                parent[find(a)] = find(b)
    joined = defaultdict(list)
    for m in narrow:
        joined[find(m)].append(m)
    out = [{'motifs': ms, 'posts': sorted(set().union(*(told[m] for m in ms)))} for ms in joined.values()]
    return sorted(out, key=lambda t: -len(t['posts'])), broad


def organize(claim: str, posts: list[str], motifs: list[str], index: dict | None = None,
             model: str = MODEL) -> dict:
    """Which of the posts tell which picked motif; when they spread, a child claim drafted for each telling.
    {'claim', 'motifs', 'posts' (how many read), 'tells' (motif -> post indexes), 'broad', 'split', 'reason',
    'children': [{'claim', 'posts' (indexes), 'motifs'}]}. Asks the filing model, so it's GPU work"""
    index = index if index is not None else mi.load()
    entries = index['entries']
    motifs = [m for m in dict.fromkeys(mi.resolve(index, m) for m in motifs) if m in entries]
    posts = [p for p in posts if p and p.strip()][:POSTS]
    out = {'claim': claim, 'motifs': motifs, 'posts': len(posts), 'tells': {}, 'broad': [], 'split': False,
           'children': [], 'model': model}
    if len(motifs) < 2:
        return {**out, 'reason': 'one motif picked'}
    if len(posts) < MIN_POSTS:
        return {**out, 'reason': f'{len(posts)} posts kept, too few to read'}
    shown = '\n'.join(f'{n}. {p[:SHOWN]}' for n, p in enumerate(posts, 1))
    listed = '\n'.join(f"{chr(65 + n)}. {mi.described(entries[m])[:300]}" for n, m in enumerate(motifs))
    r = llm.complete_json(TELLS_PROMPT.format(posts=shown, motifs=listed), tells_schema(len(motifs)),
                          max_tokens=600, model=model)
    if not r or len(r.get('tells') or []) != len(motifs):
        return {**out, 'reason': 'no answer', 'failed': True}
    out['tells'] = {m: _numbers(ps, len(posts)) for m, ps in zip(motifs, r['tells'])}
    found, broad = tellings(out['tells'])
    out['broad'] = broad
    if not found:
        return {**out, 'reason': 'no motif told by two posts or more'}
    if len(found) < 2:
        one = [m for m in motifs if m in found[0]['motifs'] or m in broad]
        names = ', '.join(entries[m]['name'] for m in one)
        return {**out, 'reason': f'one telling: {names} told by the same posts' if len(one) > 1
                else f'only {names} told in the posts'}
    found = found[:CHILDREN]
    sets = '\n\n'.join(f'Set {n}:\n' + '\n'.join(f'- {posts[i][:SHOWN]}' for i in t['posts'][:SET_POSTS])
                       for n, t in enumerate(found, 1))
    r = llm.complete_json(CHILD_PROMPT.format(n=len(found), sets=sets, wording=child_rules(index)),
                          child_schema(len(found)), max_tokens=500, model=model)
    if not r or len(r.get('claims') or []) != len(found):
        return {**out, 'reason': 'no answer', 'failed': True}
    children = []
    for t, text in zip(found, r['claims']):
        text = ' '.join((text or '').split())
        if text and mi.key(text) != mi.key(claim) and all(mi.key(text) != mi.key(c['claim']) for c in children):
            children.append({'claim': text, 'posts': t['posts'], 'motifs': t['motifs'] + broad})
    if len(children) < 2:
        return {**out, 'reason': 'the tellings were drafted as one claim'}
    names = ' / '.join(', '.join(entries[m]['name'] for m in t['motifs']) for t in found)
    return {**out, 'split': True, 'children': children, 'reason': f'told by different posts: {names}'}


# ---------- proposals ----------

def proposal_id(claim: str, motifs: list[str], split: bool = True) -> str:
    """One proposal per claim and set of picks: asked again only when the picks change"""
    return mp.pid('split' if split else 'no_split', {'claim': claim, 'motifs': sorted(motifs)})


def asked(store: dict, claim: str, motifs: list[str]) -> bool:
    return any(proposal_id(claim, motifs, s) in store for s in (True, False))


def propose(store: dict, result: dict, fired: dict | None = None, keys: list[list[str]] | None = None) -> str | None:
    """organize()'s result into the proposals store (not saved: mp.save(store) does): an open 'split', or a
    'no_split' with its reason. `keys` are each post's keys, kept with the children in place of the texts. Returns
    the proposal's id, or None for a failed reading (asked again next time)"""
    if result.get('failed'):
        return None
    claim, motifs = result['claim'], result['motifs']
    i = proposal_id(claim, motifs, result['split'])
    if i in store:
        return i
    args = {'claim': claim, 'motifs': motifs, 'triggers': fired or {}, 'posts': result['posts']}
    if result['split']:
        args['children'] = [{'claim': c['claim'], 'motifs': c['motifs'], 'posts': len(c['posts']),
                             **({'keys': [k for n in c['posts'] for k in keys[n]]} if keys else {})}
                            for c in result['children']]
    store[i] = {'id': i, 'kind': 'split' if result['split'] else 'no_split', 'args': args, 'reason': result['reason'],
                'model': result.get('model', MODEL), 'made': dt.now().isoformat(timespec='seconds'),
                'status': 'open' if result['split'] else 'none'}
    return i


def organize_claims(claims: list[str] | None = None, budget: float | None = None, since: str | None = None) -> Counter:
    """The organizer over filed claims from posts (all, or `claims`; with `since`, those dated that day or later): each
    with 2+ picks and its group's posts kept, not asked about these picks before, read and proposed. GPU work"""
    import time
    started = time.time()
    index = mi.load()
    store = mp.load()
    groups = report_groups(index)
    also = alsos()
    wanted = set(claims) if claims is not None else None
    todo = {}
    for e in mi.live(index):
        for c in e['claims']:
            if c.get('source') == 'narrative' and (wanted is None or c['claim'] in wanted) \
                    and (since is None or (c.get('date') or '') >= since):
                todo.setdefault(c['claim'], c)
    done = Counter()
    for claim, rec in todo.items():
        if budget is not None and time.time() - started > budget:
            break
        motifs = [e['id'] for e, _ in picks(index, claim)]
        if len(motifs) < 2 or asked(store, claim, motifs) or mi.key(claim) in index.get('tellings', {}):
            continue
        group = group_of(claim, rec.get('ref', ''), groups)
        posts = posts_of((group or {}).get('keys') or [])
        result = organize(claim, [p['text'] for p in posts], motifs, index)
        if propose(store, result, triggers(claim, index, group, also), [p['keys'] for p in posts]):
            done['split' if result['split'] else 'no split'] += 1
            mp.save(store)
        else:
            done['failed'] += 1
    logger.info("Claim organizer: %s", dict(done))
    return done


def still_holds(p: dict, index: dict) -> bool:
    """An open split still makes sense: its claim still filed somewhere, and not split already"""
    if p.get('kind') != 'split':  # the store holds every kind of proposal; only splits carry a claim in args
        return False
    k = mi.key(p['args']['claim'])
    return bool(mi._ids(index, k)) and k not in index.get('tellings', {})


def split_action(p: dict) -> dict:
    """The checker action that carries out a split proposal: motif_proposals.action's, with the proposal's id"""
    return {**mp.action(p), 'proposal': p['id']}


def open_splits(index: dict | None = None, texts: int = 6) -> list[dict]:
    """The open split proposals still holding, for the checker, most triggers first: each with the parent's filings
    now ({'id', 'name', 'genre', 'fit', 'checked'}), its children with up to `texts` of their posts' words (from the
    post store, while kept), and 'do', the action that carries it out"""
    from app.narratives import posts_of as texts_of
    index = index if index is not None else mi.load()
    out = []
    for p in mp.load().values():
        if p.get('status') != 'open' or not still_holds(p, index):
            continue
        claim = p['args']['claim']
        filings = [{'id': e['id'], 'name': e['name'], 'genre': mi.genre_of(e), 'fit': rec.get('fit'),
                    'checked': rec.get('checked')} for e, rec in picks(index, claim)]
        children = [{**c, 'names': [index['entries'][m]['name'] for m in c.get('motifs', []) if m in index['entries']],
                     'texts': [x['text'] for x in texts_of(c.get('keys') or [])[:texts]]}
                    for c in p['args'].get('children', [])]
        out.append({**p, 'filings': filings, 'children': children, 'do': split_action(p)})
    return sorted(out, key=lambda p: (-len(p['args'].get('triggers') or {}), p['made']))


# ---------- applying a split ----------

def _children(children) -> list[str]:
    """Child claims as given (words, or {'claim': words}), tidied, each once"""
    out = []
    for c in children or []:
        text = ' '.join(((c.get('claim') if isinstance(c, dict) else c) or '').split())
        if text and mi.key(text) not in {mi.key(x) for x in out}:
            out.append(text)
    return out


def pending(index: dict | None = None) -> list[dict]:
    """Children of applied splits not filed yet (the checker applied the split without filing them), ready for
    file_claims"""
    index = index if index is not None else mi.load()
    out = []
    for t in index.get('tellings', {}).values():
        for child in t.get('children', []):
            if mi.key(child) not in index['claims']:
                out.append({**t.get('as', {}), 'claim': child, 'split_from': t['claim']})
    return out


def refile_pending(budget: float | None = None) -> dict:
    """File the children waiting (pending()) through file_claims: GPU work"""
    todo = pending()
    return mi.file_claims(todo, limit=len(todo), budget=budget) if todo else mi.load()


def apply_split(proposal_id: str | None = None, children=None, why: str | None = None, claim: str | None = None,
                refile: bool = True) -> dict:
    """A split the person approved: the proposal's children (or `children`, the person's own words for them), or a
    hand split of `claim` with no proposal. The parent leaves every motif it was in, without a mark that it isn't that
    motif (no not_claims, never refiled), and stays in the index as the telling (index['tellings'][its key]: its
    filings as they were, its children, when, by whom); the children go to file_claims with the parent's source, ref,
    side, date and story and a split_from link (with `refile` False they wait for the hourly run, refile_pending()).
    A proposal is marked approved, with `why` and, when the person changed the children, the action carried out.
    Returns the curation log's record for it, action 'split': the checker logs it as it logs any action."""
    p = None
    if proposal_id:
        p = mp.load().get(proposal_id)
        if not p or p['kind'] != 'split':
            raise ValueError(f'no such split proposal: {proposal_id}')
        if p['status'] != 'open':
            raise ValueError(f'proposal {proposal_id} is {p["status"]} already')
        claim = p['args']['claim']
        if children is None:
            children = p['args'].get('children', [])
    if not isinstance(claim, str) or not claim.strip():
        raise ValueError('a split needs a claim')
    kids = [c for c in _children(children) if mi.key(c) != mi.key(claim)]
    if not kids:
        raise ValueError('a split needs at least one child claim other than the claim itself')
    k = mi.key(claim)
    with mi.locked():
        index = mi.load()
        if k in index.get('tellings', {}):
            raise ValueError('that claim was split already')
        if k not in index['claims']:
            raise ValueError('no such claim in the index')
        was, filings = [], []
        for eid in mi._ids(index, k):
            eid = mi.resolve(index, eid)
            entry = index['entries'].get(eid)
            rec = next((c for c in (entry or {}).get('claims', []) if mi.key(c['claim']) == k), None)
            if rec is None:
                continue
            entry['claims'].remove(rec)  # out, but not 'not this motif': no not_claims, so its children may go back in
            if 'done' in entry:
                entry['done'] = [d for d in entry['done'] if d != k]
            was.append(eid)
            filings.append({'id': eid, **rec})
        first = filings[0] if filings else {}
        carried = {f: first[f] for f in ('source', 'ref', 'side', 'date', *mi.STORY_FIELDS) if first.get(f) is not None}
        index['claims'][k] = []  # filed nowhere, and never filed again: it's the telling now
        drafted = [c['claim'] for c in (p or {}).get('args', {}).get('children', [])]
        index.setdefault('tellings', {})[k] = {
            'claim': claim, 'filings': filings, 'children': kids, 'as': carried,
            'at': dt.now().isoformat(timespec='seconds'), 'by': 'model' if p and kids == drafted else 'person',
            **({'proposal': proposal_id} if p else {}), **({'why': ' '.join(why.split())} if why and why.strip() else {})}
        mi.save(index)
    done = {'action': ACTION, 'claim': claim, 'ids': was, 'children': kids, **({'proposal': proposal_id} if p else {}),
            **({'why': ' '.join(why.split())} if why and why.strip() else {})}
    if p:
        mp.decide(proposal_id, 'approved', why, final={'action': ACTION, 'claim': claim, 'children': kids})
    if refile:
        try:
            mi.file_claims([{**carried, 'claim': c, 'split_from': claim} for c in kids], limit=len(kids))
        except Exception as e:  # noqa: BLE001 - the hourly run files what's left (refile_pending)
            logger.warning("Claim organizer: the children wait for the hourly run (%s)", e)
    return done


def reject_split(proposal_id: str, why: str | None = None):
    """A split the person turned down (kept, so it isn't proposed again for the same picks)"""
    p = mp.load().get(proposal_id)
    if not p or p['kind'] != 'split':
        raise ValueError(f'no such split proposal: {proposal_id}')
    mp.decide(proposal_id, 'rejected', why)
