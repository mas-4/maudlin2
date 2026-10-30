"""Motifs across the whole site (Oct 27, the person: "really interesting ways to incorporate the motif tagging into the
larger site ... making things more integrated"). The motif index lived on its own pages; this module joins it to the
rest, once per build, from what the index and the trackers already hold:

- tellings(): every public filing as a telling, with who told it and from which side: a show (its lean, from the
  show-claims pipeline's retold groups), people online, a fact-checker, voters in The Focus Group; and the story it
  was told about. Posts and fact-checks carry their story from their own pipelines; show claims are tied here
  (show_ties), by meaning against the stories on the front pages around the claim's date, strictly: calibrated Oct 27
  on the 392 narratives the story model tied, the nearest story at TIE_FLOOR and TIE_MARGIN over the next agreed with
  the model's story 85% of the time and with its saga 92%.
- by_story(): a story's tellings by motif, each with its sides, and the motifs that answer them.
- shows(): each show's repertoire (the motifs its claims came up in), its signature motifs (weighted log-odds against
  all the other shows, Monroe et al. 2008) and its nearest shows by what they tell (cosine of motif counts).
- people(): the motifs told about each name in the news (a name, or its alias, in the claim's words).
- spoken(): the show tellings a show's own host or guest said, one per motif per episode: what sides are counted on
  (the aisle's lean, the divide index). Each show telling carries who said it (host, guest, caller, a clip the show
  played), as the show-claims pipeline heard it.
- lexicon() / words_in(): the motifs' names and tellers' phrases spotted in headlines and TV captions, word for word.

Nothing here asks a model to judge anything; show_ties embeds claims and story labels (mxbai, cached)."""
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np

from app.analysis import motif_index as mi
from app.utils import get_logger
from app.utils.config import Config
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

TIES = os.path.join(Config.data, 'show_story_ties.json')  # claim key -> story id, or 0 for none (asked once)
TIE_FLOOR, TIE_MARGIN = 0.75, 0.04
WINDOW_BEFORE, WINDOW_AFTER = 2, 1  # days: stories on the front pages around the claim's date
SIDES = ('left', 'center', 'right')
ANSWER = re.compile(r'answer|counter|mirror|rebut|retort', re.I)
CHECKERS = {'Snopes', 'Lead Stories', 'PolitiFact', 'Full Fact', 'FactCheck.org', 'NewsGuard Reality Check',
            'Science Feedback', 'Check Your Fact', 'AFP Fact Check'}
MIN_SHOW_CLAIMS = 8  # a show needs this many claims in public motifs for a repertoire page
SIGNATURE, NEIGHBOURS = 8, 5
PRIOR = 10  # the prior's weight in counts, spread over the motifs by their share of every show's tellings


def public_entries(index: dict) -> dict:
    """The motifs the site shows: verified, not watch lists (Straight news), each with only its public claims"""
    bins = mi.watched(index)
    return {e['id']: {**e, 'claims': mi.public_claims(e)} for e in mi.live(index)
            if mi.public(e) and e['id'] not in bins}


SPEAKERS = ('host', 'guest', 'caller', 'clip')  # who said it on a show: the show's own voice first
# Sides are counted on what a show's own host or guest said (Oct 28, the moonshot probe: 667 show tellings were clips
# a show played, often to rebut them, as left shows playing the attack ad on Amy Acton). Guests count too: the show
# booked them, center shows' tellings are 44% guest, and host-only counting halves the sample for no change in the
# divide (excess 0.25 host-only, 0.24 host or guest). Callers are listeners, not the show
SPOKEN = ('host', 'guest')


def said_by(speakers) -> str:
    """The speaker that counts most among a show's tellings of one claim (SPEAKERS order), or ''"""
    return next((s for s in SPEAKERS if s in speakers), '')


def show_tellers() -> dict[str, list[dict]]:
    """claim key -> every show telling of its retold group: [{show, source, lean, date, url, speaker}], each show once
    (its first episode, and the speaker counting most among its tellings)"""
    from app.analysis import show_claims
    episodes = show_claims.load()
    out = {}
    for g in show_claims.kept_retold():
        told, speakers = {}, defaultdict(set)
        for t in g.get('told', []):
            ep = episodes.get(t.get('url'), {})
            show = t.get('show') or ep.get('show')
            if not show:
                continue
            speakers[show].add(t.get('speaker') or '')
            told.setdefault(show, {'show': show, 'source': ep.get('source', ''), 'lean': ep.get('lean') or '',
                                   'date': ep.get('date', ''),
                                   'url': t['url'] if str(t.get('url', '')).startswith('http') else ''})
        told = [{**t, 'speaker': said_by(speakers[show])} for show, t in told.items()]
        for claim in [g['claim']] + [t['claim'] for t in g.get('told', []) if t.get('claim')]:
            out.setdefault(mi.key(claim), told)
    # a claim no retold group holds: the episode its filing came from (filled in tellings())
    return out


def stories_around() -> list[dict]:
    """Every labelled story with its days on the front pages: [{id, label, first, last, saga}]"""
    from app.models import Session, Story
    with Session() as s:
        return [{'id': i, 'label': lab, 'first': f.date().isoformat(), 'last': last.date().isoformat(), 'saga': sg}
                for i, lab, f, last, sg in s.query(Story.id, Story.label, Story.first_seen, Story.last_seen, Story.saga_id)
                if lab]


def show_ties(claims: list[dict], stories: list[dict]) -> dict[str, int]:
    """claim key -> the story a show claim was told about (0: none close enough), cached: each claim asked once"""
    ties = read_json(TIES, {})
    todo = [c for c in claims if mi.key(c['claim']) not in ties and c.get('date')]
    if todo and stories:
        from app.narratives import embed
        V = embed([s['label'] for s in stories])
        V = V / np.linalg.norm(V, axis=1, keepdims=True)
        C = embed([c['claim'] for c in todo])
        C = C / np.linalg.norm(C, axis=1, keepdims=True)
        first = np.array([s['first'] for s in stories])
        last = np.array([s['last'] for s in stories])
        for c, sims in zip(todo, C @ V.T):
            day = datetime.fromisoformat(str(c['date'])[:10])
            lo = (day - timedelta(days=WINDOW_BEFORE)).date().isoformat()
            hi = (day + timedelta(days=WINDOW_AFTER)).date().isoformat()
            near = np.where((first <= hi) & (last >= lo), sims, -1.0)
            order = np.argsort(-near)
            best = near[order[0]]
            second = near[order[1]] if len(order) > 1 else -1.0
            ties[mi.key(c['claim'])] = int(stories[order[0]]['id']) \
                if best >= TIE_FLOOR and best - second >= TIE_MARGIN else 0
        write_json(TIES, ties)
        logger.info("Show claims tied to stories: %d new, %d tied", len(todo),
                    sum(1 for c in todo if ties[mi.key(c['claim'])]))
    return {k: v for k, v in ties.items() if v}


def tellings(index: dict | None = None, tie: bool = True) -> list[dict]:
    """Every public filing as one row per teller: {motif, name, genre, claim, key, kind ('shows', 'posts', 'check',
    'voters'), teller, side ('left', 'center', 'right' or None), date, story (id or None), url}; show rows also carry
    speaker (SPEAKERS, or '' when not known)"""
    from app.analysis import show_claims
    from app.analysis.stories import merges
    index = index if index is not None else mi.load()
    entries = public_entries(index)
    tellers = show_tellers()
    episodes = show_claims.load()
    gone = merges()
    show_claims_seen = [c for e in entries.values() for c in e['claims'] if c.get('source') == 'shows']
    ties = show_ties(show_claims_seen, stories_around()) if tie else {}
    rows = []
    for e in entries.values():
        genre = mi.person_genre(e) or ''
        for c in e['claims']:
            k = mi.key(c['claim'])
            story = c.get('story')
            src = c.get('source', '')
            base = {'motif': e['id'], 'name': e['name'], 'genre': genre, 'claim': c['claim'], 'key': k,
                    'date': str(c.get('date', ''))[:10]}
            if src == 'shows':
                story = ties.get(k)
                told = tellers.get(k)
                if not told:
                    ep = episodes.get(c.get('ref'), {})
                    said = {x.get('speaker') or '' for x in ep.get('claims', []) if mi.key(x.get('claim', '')) == k}
                    told = [{'show': ep['show'], 'source': ep.get('source', ''), 'lean': ep.get('lean') or '',
                             'date': ep.get('date', ''), 'url': c['ref'] if str(c.get('ref', '')).startswith('http') else '',
                             'speaker': said_by(said)}] if ep.get('show') else []
                for t in told:
                    rows.append({**base, 'kind': 'shows', 'teller': t['show'], 'show_source': t['source'],
                                 'side': t['lean'] if t['lean'] in SIDES else None, 'url': t['url'],
                                 'speaker': t.get('speaker', ''),
                                 'date': t['date'] or base['date'],
                                 'story': gone.get(int(story), int(story)) if story else None})
                continue
            kind = 'posts' if src == 'narrative' else 'voters' if src == 'Focus Group' else 'check'
            rows.append({**base, 'kind': kind, 'teller': 'people online' if kind == 'posts' else src, 'side': None,
                         'url': c.get('ref') if kind == 'check' and str(c.get('ref', '')).startswith('http') else '',
                         'story': gone.get(int(story), int(story)) if story is not None else None})
    return rows


def spoken(rows: list[dict]) -> list[dict]:
    """The show tellings a show's own host or guest said (SPOKEN), one per motif per show episode: the rows sides are
    counted on. Clips a show played, callers and tellings whose speaker isn't known are left out"""
    seen, out = set(), []
    for r in rows:
        if r['kind'] != 'shows' or r.get('speaker') not in SPOKEN:
            continue
        k = (r['motif'], r['teller'], r['url'] or r['date'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def answers(index: dict, entries: dict) -> dict[str, list[dict]]:
    """motif -> the public motifs a person linked to it as its answer or mirror: [{id, name, note}]"""
    notes = index.get('related_notes', {})
    out = defaultdict(list)
    for a, b in index.get('related', []):
        note = notes.get(f'{a}|{b}') or notes.get(f'{b}|{a}') or ''
        if ANSWER.search(note) and a in entries and b in entries:
            out[a].append({'id': b, 'name': entries[b]['name'], 'note': note})
            out[b].append({'id': a, 'name': entries[a]['name'], 'note': note})
    return out


def sided(rows: list[dict]) -> dict:
    """Who told a set of tellings: {left, center, right: [shows]}, posts (claims retold online), checks (checkers),
    voters"""
    shows = {s: sorted({r['teller'] for r in rows if r['kind'] == 'shows' and r['side'] == s}) for s in SIDES}
    return {**shows, 'other_shows': sorted({r['teller'] for r in rows if r['kind'] == 'shows' and not r['side']}),
            'posts': len({r['key'] for r in rows if r['kind'] == 'posts'}),
            'checks': sorted({r['teller'] for r in rows if r['kind'] == 'check'}),
            'voters': len({r['key'] for r in rows if r['kind'] == 'voters'})}


def by_story(rows: list[dict], index: dict, entries: dict) -> dict[int, list[dict]]:
    """story id -> its motifs, most told first: [{id, name, genre, sides (sided), claims, answers, first}]"""
    ans = answers(index, entries)
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['story']:
            grouped[r['story']][r['motif']].append(r)
    out = {}
    for sid, motifs in grouped.items():
        items = []
        for m, rs in motifs.items():
            items.append({'id': m, 'name': rs[0]['name'], 'genre': rs[0]['genre'], 'sides': sided(rs),
                          'claims': sorted({r['claim'] for r in rs}), 'first': min(r['date'] for r in rs),
                          'tellers': len({r['teller'] for r in rs}),
                          'answers': [a for a in ans.get(m, []) if a['id'] in motifs] or ans.get(m, [])[:2]})
        out[sid] = sorted(items, key=lambda i: (-i['tellers'], i['name']))
    return out


def by_motif_stories(rows: list[dict]) -> dict[str, list[int]]:
    """motif -> the stories its tellings were about, most tellings first"""
    count = defaultdict(Counter)
    for r in rows:
        if r['story']:
            count[r['motif']][r['story']] += 1
    return {m: [s for s, _ in c.most_common()] for m, c in count.items()}


def shows(rows: list[dict]) -> dict[str, dict]:
    """show -> {lean, source, claims, motifs [(id, name, n)], signature [(id, name, z)], neighbours [(show, sim)]}"""
    counts = defaultdict(Counter)
    meta, names, claims = {}, {}, defaultdict(set)
    for r in rows:
        if r['kind'] != 'shows':
            continue
        counts[r['teller']][r['motif']] += 1
        claims[r['teller']].add(r['key'])
        names[r['motif']] = r['name']
        meta.setdefault(r['teller'], {'lean': r['side'], 'source': r.get('show_source', '')})
    kept = [s for s in counts if len(claims[s]) >= MIN_SHOW_CLAIMS]
    total = Counter()
    for s in counts:
        total.update(counts[s])
    n_all = sum(total.values())
    vocab = sorted(total)
    vec = {s: np.array([counts[s][m] for m in vocab], dtype=float) for s in kept}
    alpha = {m: 1 + PRIOR * total[m] / n_all for m in vocab}  # an informative prior: a little of the whole corpus
    a0 = sum(alpha.values())
    out = {}
    for s in kept:
        n_s, n_o = sum(counts[s].values()), n_all - sum(counts[s].values())
        z = []
        for m in counts[s]:
            y_s, y_o = counts[s][m], total[m] - counts[s][m]
            d = (math.log((y_s + alpha[m]) / (n_s + a0 - y_s - alpha[m]))
                 - math.log((y_o + alpha[m]) / (n_o + a0 - y_o - alpha[m])))
            var = 1 / (y_s + alpha[m]) + 1 / (y_o + alpha[m])
            if y_s >= 2:
                z.append((m, names[m], d / math.sqrt(var)))
        v = vec[s] / (np.linalg.norm(vec[s]) or 1)
        sims = sorted(((o, float(v @ (vec[o] / (np.linalg.norm(vec[o]) or 1)))) for o in kept if o != s),
                      key=lambda x: -x[1])
        out[s] = {**meta[s], 'show': s, 'claims': len(claims[s]),
                  'motifs': [(m, names[m], n) for m, n in counts[s].most_common()],
                  'signature': sorted(z, key=lambda x: -x[2])[:SIGNATURE],
                  'neighbours': sims[:NEIGHBOURS]}
    return out


def show_slug(show: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', show.lower()).strip('-')


def people(rows: list[dict], names: list[str], aliases: dict[str, str]) -> dict[str, list[dict]]:
    """name -> the motifs told about it (its name or an alias in the claim's words), most claims first:
    [{id, name, claims, sides}]"""
    spellings = defaultdict(set)
    for n in names:
        spellings[n].add(n)
    for alias, canon in aliases.items():
        if canon in spellings and len(alias) > 3:
            spellings[canon].add(alias)
    pats = {n: re.compile(r'\b(?:' + '|'.join(re.escape(s) for s in sorted(sp, key=len, reverse=True)) + r')\b', re.I)
            for n, sp in spellings.items()}
    by_claim = defaultdict(list)
    for r in rows:
        by_claim[r['key']].append(r)
    out = defaultdict(lambda: defaultdict(list))
    for rs in by_claim.values():
        text = rs[0]['claim']
        for n, p in pats.items():
            if p.search(text):
                for r in rs:
                    out[n][r['motif']].append(r)
    result = {}
    for n, motifs in out.items():
        items = [{'id': m, 'name': rs[0]['name'], 'claims': len({r['key'] for r in rs}), 'sides': sided(rs)}
                 for m, rs in motifs.items()]
        result[n] = sorted(items, key=lambda i: (-i['claims'], i['name']))
    return result


# Words that name a motif in so many words, spotted in headlines and captions: its name or a teller's phrase, at least
# two words long (single words like "Inflation" or "Sanctions" are topics more often than tellings). Not Plots or the
# everyday talk: a plot's name is what a report says plainly ("found dead", "mass shooting", "data breach", Oct 27
# on three days of headlines), where an argument's or a theory's ("rigged election", "radical left", "deep state")
# is the telling itself
LEXICON_MIN_WORDS = 2
LEXICON_GENRES = {'Archetypes', 'Beliefs', 'Theories', 'Arguments', 'Values', 'Exhortations'}
LEXICON_SKIP = {'straight news', 'on the ground', "that's why", 'lights out'}


def lexicon(entries: dict) -> dict[str, tuple[str, str]]:
    """phrase (lowercase) -> (motif id, motif name)"""
    out = {}
    for e in entries.values():
        if (mi.person_genre(e) or '') not in LEXICON_GENRES:
            continue
        for phrase in [e['name']] + [p for p, _ in mi.carrying(e)]:
            p = re.sub(r'[!?.,:;]+$', '', phrase.strip().lower())
            if len(p.split()) >= LEXICON_MIN_WORDS and p not in LEXICON_SKIP:
                out.setdefault(p, (e['id'], e['name']))
    return out


def lexicon_pattern(lex: dict) -> re.Pattern | None:
    return re.compile(r'\b(' + '|'.join(re.escape(p) for p in sorted(lex, key=len, reverse=True)) + r')\b', re.I) \
        if lex else None


def words_in(items: list, lex: dict[str, tuple[str, str]], pat: re.Pattern | None = None) -> list[dict]:
    """The motif phrases found word for word in `items` (texts, or (text, group) pairs: a channel, a lean), each item
    counted once a phrase: [{phrase, id, name, n, by: {group: n}}], most found first"""
    pat = pat or lexicon_pattern(lex)
    if pat is None or not items:
        return []
    found, by = Counter(), defaultdict(Counter)
    for it in items:
        text, group = (it, None) if isinstance(it, str) else it
        for m in {x.lower() for x in pat.findall(text or '')}:
            found[m] += 1
            if group:
                by[m][group] += 1
    return [{'phrase': p, 'id': lex[p][0], 'name': lex[p][1], 'n': n, 'by': dict(by[p].most_common())}
            for p, n in found.most_common()]


def build(tie: bool = True) -> dict:
    """Everything the pages need, once: {index, entries, rows, stories (by_story), motif_stories, shows, answers,
    lexicon}. No "the answer took N days" (Oct 28): in the Oct 27 probe the answer came after its move in 26 of 47
    pairs, against 26.5 expected from the motifs' sizes alone, so the order mostly says which motif is bigger"""
    index = mi.load()
    entries = public_entries(index)
    rows = tellings(index, tie=tie)
    lex = lexicon(entries)
    return {'index': index, 'entries': entries, 'rows': rows, 'stories': by_story(rows, index, entries),
            'motif_stories': by_motif_stories(rows), 'shows': shows(rows), 'answers': answers(index, entries),
            'lexicon': lex, 'pattern': lexicon_pattern(lex)}


def recent_headlines(days: int = 3) -> list[tuple[str, str]]:
    """(headline, its outlet's lean: left, center, right or not rated) seen on the front pages in the last `days`"""
    from app.models import Session, Headline, Article, Agency
    since = datetime.utcnow() - timedelta(days=days)
    lean = {-3: 'left', -2: 'left', -1: 'left', 0: 'center', 1: 'right', 2: 'right', 3: 'right'}
    with Session() as s:
        rows = s.query(Headline.title, Agency._bias, Agency.lean_rated).join(Headline.article).join(Article.agency) \
            .filter(Headline.first_accessed > since).all()  # noqa
    return [(t, lean.get(b, 'not rated') if rated else 'not rated') for t, b, rated in rows if t]


def recent_captions(days: int = 3) -> list[tuple[str, str]]:
    """(TV caption, its channel) of the last `days` days read"""
    import glob
    from app import chyrons
    out = []
    for path in sorted(glob.glob(os.path.join(chyrons.FOLDER, 'matched-*.json')))[-days:]:
        for c in read_json(path, []):
            out.append((c['text'], chyrons.CHANNELS.get(c['channel'], c['channel'])))
    return out


def words_by_motif(found: list[dict]) -> dict[str, list[dict]]:
    """words_in's finds grouped by motif"""
    out = defaultdict(list)
    for f in found:
        out[f['id']].append(f)
    return out


def checked_vs_told(rows: list[dict], least: int = 4, top: int = 12) -> dict:
    """What the fact-checkers spend their time on, against what's told: per motif, the distinct claims told on the
    shows and online, and the claims fact-checkers examined. {'unchecked': the most told with no check (a lead list
    for checkers; not everyday talk, which has nothing to check), 'checked': the most checked, each [{id, name, told,
    checked, posts, left, right}]}, left and right counting the shows whose host or guest said it (spoken)"""
    told, checked, by = defaultdict(set), defaultdict(set), defaultdict(list)
    for r in rows:
        by[r['motif']].append(r)
        if r['kind'] in ('shows', 'posts'):
            told[r['motif']].add(r['key'])
        elif r['kind'] == 'check':
            checked[r['motif']].add(r['key'])
    items = []
    for m, rs in by.items():
        said = sided(spoken(rs))
        items.append({'id': m, 'name': rs[0]['name'], 'genre': rs[0]['genre'], 'told': len(told[m]),
                      'checked': len(checked[m]), 'posts': len({r['key'] for r in rs if r['kind'] == 'posts'}),
                      'left': len(said['left']), 'right': len(said['right'])})
    unchecked = sorted((i for i in items if i['checked'] == 0 and i['told'] >= least and i['genre'] != 'Perennials'),
                       key=lambda i: (-i['told'], i['name']))[:top]
    most = sorted((i for i in items if i['checked']), key=lambda i: (-i['checked'], -i['told']))[:top]
    return {'unchecked': unchecked, 'checked': most}


def voters_only(rows: list[dict], top: int = 15) -> list[dict]:
    """The motifs only voters told (The Focus Group), told by no show, online or checker we follow: [{id, name,
    claims}], the most claims first"""
    by = defaultdict(list)
    for r in rows:
        by[r['motif']].append(r)
    out = [{'id': m, 'name': rs[0]['name'], 'claims': len({r['key'] for r in rs})}
           for m, rs in by.items() if all(r['kind'] == 'voters' for r in rs)]
    return sorted(out, key=lambda i: (-i['claims'], i['name']))[:top]


def cloud(rows: list[dict], days: int = 7, most: int = 60) -> list[dict]:
    """The front page's cloud of stories told: the motifs told in the last `days`, sized by how many tellers told
    them, colored by which side's shows did (blue left, red right, both, grey neither), each a link to its page; the
    word cloud's own fields (text, outlets as the size, color, lean, spice, tip)"""
    from app.site.common import motif_href
    since = (datetime.now() - timedelta(days=days)).date().isoformat()
    recent = defaultdict(list)
    for r in rows:
        if r['date'] >= since and r['genre'] != 'Perennials':
            recent[r['motif']].append(r)
    out = []
    for m, rs in recent.items():
        s = sided(rs)
        left, right = len(s['left']), len(s['right'])
        if left and right and min(left, right) / max(left, right) >= 1 / 3:
            color, lean = 'balanced', 0
        elif left > right:
            color, lean = '#1a5cff', -1
        elif right > left:
            color, lean = '#e0102e', 1
        else:
            color, lean = '#8a8f98', 0
        tellers = len({(r['kind'], r['teller'], r['key']) for r in rs})
        out.append({'id': m, 'text': rs[0]['name'], 'outlets': tellers, 'color': color, 'lean': lean, 'spice': 0,
                    'url': motif_href(m),
                    'tip': f"{rs[0]['name']}: told {tellers} times this week"
                           + (f"; on {left} left and {right} right shows" if left or right else '')
                           + ' (a story people tell, not a claim that it is true)'})
    return sorted(out, key=lambda w: -w['outlets'])[:most]
