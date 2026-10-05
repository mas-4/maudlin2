"""Who and what the current stories are about: the people, countries, places, organizations and groups each story
names, so unrelated stories about the same subject can be found together (several Russia stories, several Yemen
ones). The local model reads a few of a story's headlines and names the main ones (up to MAX), each by its common
short name so the same subject is named the same way in every story; names are remembered per saved story.

These groups are not sagas (app/analysis/sagas.py): a saga links the parts of one running story; an entity group is
every current story that names the same subject, related or not."""
import hashlib
import os
import re

from app.analysis import llm
from app.analysis.textnorm import source_suffix
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

CACHE = os.path.join(Config.data, 'story_entities.json')  # story key -> [names]
# One name per subject (#165): the model names a subject differently from story to story ('Trump', 'Donald Trump';
# 'GOP', 'Republican Party'), so names pass through aliases to one canonical name. A person merges, renames and keeps
# apart names in the organizer on the label-check page (scripts/validate.py); those choices live in this file and
# win over the seeds below.
ALIASES = os.path.join(Config.data, 'entity_aliases.json')  # {'aliases': {lowercase name: name}, 'not_same': [[a, b]]}
SEED_ALIASES = {
    'trump': 'Donald Trump', 'president trump': 'Donald Trump', 'donald j. trump': 'Donald Trump',
    'gop': 'Republican Party', 'republicans': 'Republican Party', 'the gop': 'Republican Party',
    'democrats': 'Democratic Party', 'democratic party': 'Democratic Party',
    'supreme court of the united states': 'Supreme Court', 'scotus': 'Supreme Court',
    'u.s. supreme court': 'Supreme Court', 'us supreme court': 'Supreme Court',
}
MAX = 6
MAX_NEW = 120  # model calls a run, at most
PROMPT = """These headlines are about one news story:
{headlines}

Which people, countries, places, organizations and groups is this story about? Name only ones the headlines name, \\
at most six, the most central first. Name each the way American news most commonly names it, so the same subject \\
always gets the same name: a person by full name, unless one name alone is how they're universally known; a country \\
by its own name, rather than its government, capital, leader's office or people; an organization by its usual short \\
name; a group by its own name. Leave out generic roles (police, officials, voters, a judge) and words that aren't \\
names."""
SCHEMA = {"type": "object", "properties": {"names": {"type": "array", "maxItems": MAX,
                                                     "items": {"type": "string", "maxLength": 40}}},
          "required": ["names"]}


# On a US-centric front page nearly every story is about the United States: not a group worth a filter
EVERYWHERE = {'united states', 'u.s', 'u.s.', 'us', 'usa', 'america', 'united states of america'}
FILLER = {'the', 'of', 'and', 'for', 'new', 'national', 'department', 'party', 'state', 'states', 'united', 'news'}


def named_in(name: str, text: str) -> bool:
    """Whether the headlines actually name it (the model adds names they don't: OPEC+ came back with Russia, Iran
    and Iraq): one of its distinctive words appears in them, e.g. 'Houthis' in 'Houthi rebels', 'Russia' in
    'Russian'."""
    words = [w for w in re.findall(r"[a-z0-9+']+", name.lower()) if len(w) >= 3 and w not in FILLER]
    return any(w.rstrip('s') in text for w in words)


def load_aliases() -> dict:
    book = read_json(ALIASES, {})
    return {'aliases': {**SEED_ALIASES, **book.get('aliases', {})}, 'not_same': book.get('not_same', [])}


def save_aliases(book: dict):
    """Only what a person chose: the seeds stay in the code"""
    mine = {k: v for k, v in book['aliases'].items() if SEED_ALIASES.get(k) != v}
    write_json(ALIASES, {'aliases': mine, 'not_same': book['not_same']}, indent=1, sort_keys=True)


def canonical(name: str, aliases: dict) -> str:
    """The name a subject goes by, following aliases (a chain at most a few long; a loop stops where it began)"""
    seen = set()
    while name.lower() in aliases and name.lower() not in seen:
        seen.add(name.lower())
        name = aliases[name.lower()]
    return name


def tidy(name: str) -> str:
    name = re.sub(r'^(the|The)\s+', '', name.strip()).strip(' .,;:"\'')
    return name[:1].upper() + name[1:] if name else ''


def of_stories(stories: dict, limit: int = MAX_NEW) -> dict:
    """story key -> its names. `stories`: key (a saved story's id, or the cluster's) -> its headlines."""
    cache = read_json(CACHE, {})
    out, asked = {}, 0
    aliases = load_aliases()['aliases']
    for k, headlines in stories.items():
        k = str(k)
        # Without the feed's source tag: '... - AP News' made 'AP News' a name in AP's stories
        every = list(dict.fromkeys(source_suffix(h.strip()) for h in headlines if h and h.strip()))
        shown = every[:5]
        text = ' '.join(shown).lower()
        if k not in cache:
            if asked >= limit or llm.backend() is None:
                continue
            asked += 1
            answer = llm.complete_json(PROMPT.format(headlines='\n'.join(f'- {h}' for h in shown)), SCHEMA,
                                       max_tokens=120)
            if not answer:
                continue
            cache[k] = list(dict.fromkeys(n for n in (tidy(x) for x in answer['names'])
                                          if len(n) > 1 and n.lower() not in EVERYWHERE and named_in(n, text)))[:MAX]
        # Rechecked against all its headlines, so names cached before a fix drop out; then each by its canonical name
        out[k] = list(dict.fromkeys(canonical(n, aliases) for n in cache[k] if named_in(n, ' '.join(every).lower())))
    if asked:
        write_json(CACHE, cache)
    logger.info("Entities: %d stories named (%d new model calls)", len(out), asked)
    return out


def groups(named: dict, least: int = 2) -> list[tuple[str, list]]:
    """(name, [story keys]) for every name in at least `least` stories, most stories first. Names differing only in
    case are one."""
    found = {}
    for k, names in named.items():
        for n in names:
            found.setdefault(n.lower(), {'name': n, 'stories': []})['stories'].append(k)
    return sorted(((g['name'], g['stories']) for g in found.values() if len(set(g['stories'])) >= least),
                  key=lambda g: (-len(g[1]), g[0]))


def all_names() -> dict[str, int]:
    """Every name the model has given a saved or current story, as it gave it, with how many stories have it."""
    cache = read_json(CACHE, {})
    counts = {}
    for names in cache.values():
        for n in set(names):
            counts[n] = counts.get(n, 0) + 1
    return counts


def suggestions() -> list[tuple[str, str]]:
    """(name, the name it may be another name for), for the organizer: a name inside another, whole words ('Trump'
    in 'Donald Trump', 'Supreme Court' in 'Supreme Court of the United States'), not already one subject and not
    marked as different subjects. Most-used pairs first."""
    book = load_aliases()
    counts = {}
    for n, c in all_names().items():
        name = canonical(n, book['aliases'])
        counts[name] = counts.get(name, 0) + c
    apart = {frozenset(map(str.lower, pair)) for pair in book['not_same']}
    found = []
    for a in counts:
        for b in counts:
            if a.lower() != b.lower() and f' {a.lower()} ' in f' {b.lower()} ' \
                    and frozenset([a.lower(), b.lower()]) not in apart:
                found.append((counts[a] + counts[b], a, b))
    return [(a, b) for _, a, b in sorted(found, key=lambda f: (-f[0], f[1]))]


def merge(source: str, target: str):
    """`source` is another name for `target` (or a rename, when `target` is a new name)"""
    book = load_aliases()
    if source.lower() == target.lower():
        return
    if canonical(target, book['aliases']).lower() == source.lower():
        book['aliases'][target.lower()] = target  # renamed to one of its own other names: that name leads now
    else:
        target = canonical(target, book['aliases'])
    book['aliases'][source.lower()] = target
    save_aliases(book)


def not_same(a: str, b: str):
    book = load_aliases()
    book['not_same'].append(sorted([a, b]))
    save_aliases(book)


def unmerge(name: str):
    """`name` is its own subject again (a seed alias stays undone: it maps to itself)"""
    book = load_aliases()
    book['aliases'][name.lower()] = name
    save_aliases(book)


def saved_story_headlines() -> dict:
    """Every saved story's headlines, keyed as of_stories keys them ('s' + its id)"""
    from app.models import Session, Story, StoryHeadline, Headline
    with Session() as s:
        rows = s.query(Story.id, Headline.title).join(StoryHeadline, StoryHeadline.story_id == Story.id).join(
            Headline, Headline.id == StoryHeadline.headline_id).all()
    out = {}
    for sid, title in rows:
        out.setdefault(f's{sid}', []).append(title)
    return out


def history(least: int = 2) -> list[dict]:
    """Each name over time, for the names page: every saved story that names it (by its canonical name) with when it
    was on the front pages and how many outlets had it, and the outlets on all of them by lean. Names in at least
    `least` stories, most stories first. Uses the names already found (of_stories), asking the model nothing."""
    from app.models import Session, Story, StoryHeadline, Headline, Article, Agency
    cache = read_json(CACHE)
    if cache is None:
        return []
    aliases = load_aliases()['aliases']
    with Session() as s:
        stories = {f's{sid}': {'id': sid, 'label': label, 'first': first, 'last': last}
                   for sid, label, first, last in s.query(Story.id, Story.label, Story.first_seen, Story.last_seen)}
        rows = s.query(StoryHeadline.story_id, Agency.name, Agency._bias, Agency.lean_rated).join(
            Headline, Headline.id == StoryHeadline.headline_id).join(Article, Article.id == Headline.article_id).join(
            Agency, Agency.id == Article.agency_id).all()
    outlets = {}
    for sid, agency, bias, rated in rows:
        side = ('left' if bias < 0 else 'right' if bias > 0 else 'center') if rated else 'unrated'
        outlets.setdefault(f's{sid}', {})[agency] = side
    names = {}
    for k, found in cache.items():
        if k not in stories:
            continue  # a cluster key, never saved as a story
        for n in dict.fromkeys(canonical(x, aliases) for x in found):
            if n.lower() in EVERYWHERE:
                continue
            entry = names.setdefault(n.lower(), {'name': n, 'stories': [], 'outlets': {}})
            st = stories[k]
            entry['stories'].append({**st, 'outlets': len(outlets.get(k, {}))})
            entry['outlets'].update(outlets.get(k, {}))
    out = []
    for e in names.values():
        if len(e['stories']) < least:
            continue
        e['stories'].sort(key=lambda st: st['first'])
        sides = {side: sum(1 for v in e['outlets'].values() if v == side) for side in ('left', 'center', 'right', 'unrated')}
        out.append({'name': e['name'], 'stories': e['stories'], 'first': e['stories'][0]['first'],
                    'last': max(st['last'] for st in e['stories']), 'outlets': len(e['outlets']), **sides})
    return sorted(out, key=lambda e: (-len(e['stories']), e['name']))
