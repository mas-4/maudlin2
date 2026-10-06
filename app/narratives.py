"""Folklore-shaped narratives in what people say (#142, #145), from the Bluesky and Mastodon sample (app/vernacular.py).

Folklore travels as variants: the same claim, rumor, joke or saying told by many unrelated people, each in their own
words. Copypasta and coordinated posting travel as the same words from few hands. So:

1. Paraphrase groups: posts are embedded (mxbai-embed-large on the GPU) and linked to their nearest neighbours; only
   mutual neighbours above SIMILARITY join, so one generic post can't chain unrelated groups together.
2. Each group gets two numbers: how many distinct people posted it, and how varied its wording is (one minus the
   mean word overlap between its versions). Many people and varied wording: a candidate narrative. The same text
   from a few: copypasta, listed apart.
3. The local language model reads up to SAMPLE versions of each big candidate and says what claim they share, whether
   it's a retold narrative (a story, rumor or saying people repeat) or just a shared topic, its genre, its chapter
   of Thompson's Motif-Index and a specific motif, who is cast as villain, victim, hero and helper (Propp's roles),
   and whether it's about politics, from which side. Answers are cached by the versions shown.
4. Cross-checks: today's news stories (which story it rides on, if any) and the Focus Group transcripts (research
   only: they rarely overlap a day of social posts, and a yes-or-no check matched nearly anything, so the voters'
   check is a forced choice and isn't shown on the site). The nearest few by embedding are only candidates: the model, shown both side by side,
   says whether a story is the same event or the same issue (anything looser isn't shown), and whether voters voice
   the same claim; otherwise the report says there's none.

Writes a report to data/narratives/ (JSON and Markdown); nothing here is published. Run:
    .venv/bin/python -m app.narratives [--hours 6]
"""
import argparse
import glob
import hashlib
import json
import os
import random
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td, timezone

import numpy as np

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
JUDGMENTS = os.path.join(FOLDER, 'judgments.json')
EMBEDDER = 'minishlab/potion-base-32M'
SIMILARITY = 0.78  # mutual neighbours this alike (mxbai) are versions of one thing
NEIGHBOURS = 15
MIN_AUTHORS = 5
MIN_CHARS = 40
MIN_WORDS = 6  # words of letters: a string of emoji and a link has none
FEED_POSTS = 20  # posts in six hours: more is a feed or a bot
SAMPLE = 10  # versions shown to the model
LABEL_TOP = 150  # biggest candidate groups labeled per report
FOLK_VARIETY = 0.5  # wording at least this varied: told, not pasted
COPY_VARIETY = 0.2  # under this: the same words
GENRES = ['rumor', 'contemporary legend', 'conspiracy theory', 'folk belief', 'prophecy or prediction',
          'cautionary tale', 'atrocity story', 'trickster tale', 'joke formula or meme', 'proverb or catchphrase',
          'personal testimony', 'news report or shared reaction',
          'none: a shared topic, not a retold narrative']
MOTIF_CHAPTERS = ['A Mythological motifs', 'B Animals', 'C Tabu', 'D Magic', 'E The dead', 'F Marvels', 'G Ogres',
                  'H Tests', 'J The wise and the foolish', 'K Deceptions', 'L Reversal of fortune',
                  'M Ordaining the future', 'N Chance and fate', 'P Society', 'Q Rewards and punishments',
                  'R Captives and fugitives', 'S Unnatural cruelty', 'T Sex', 'U The nature of life',
                  'V Religion', 'W Traits of character', 'X Humor', 'Z Miscellaneous groups of motifs', 'none']
PROMPT = """These posts were written by different people:
{posts}

Do they retell the same narrative (one claim, rumor, legend, belief, joke or saying that people repeat in their own
words), or do they only share a topic? Reporting or reacting to the same news event is "news report or shared
reaction", not a legend or rumor: a legend or rumor is a story told as true that isn't plain reporting of the day's
news. A claim made in only one or two of the posts is not their narrative. Answer in the fields below.

narrative: the claim or story most of the posts share, in one plain sentence, or "" if there is none
retold: true if most of the posts retell that one narrative, false if they only share a topic
genre: one of {genres}
motif_chapter: the chapter of Thompson's Motif-Index it fits best, one of {chapters}
motif: the specific motif in a few words of your own, describing these posts, or ""
{shapes}
For the parts below, take the point of view of the people telling the narrative: how THEY cast it, whether or not
it's true. Many stories have no villain, no victim or no hero; say so rather than filling a part.
has_villain: does the story, as its tellers tell it, cast someone as the villain who does harm?
villain: who, or "" if not
has_victim: does it cast someone as the victim who suffers harm?
victim: who, or "" if not
has_hero: does it cast someone as the hero or rescuer who sets things right?
hero: who, or "" if not
politics: true if it is about politics or public life
side: whose politics the people telling it carry: "left", "right", "both" or "none" (no politics)"""
from app.analysis.rumor_shapes import SCHEMA_FIELDS as SHAPE_FIELDS, prompt_fields, settle  # noqa: E402

SCHEMA = {"type": "object", "properties": {
    "narrative": {"type": "string"}, "retold": {"type": "boolean"}, "genre": {"type": "string", "enum": GENRES},
    "motif_chapter": {"type": "string", "enum": MOTIF_CHAPTERS}, "motif": {"type": "string"},
    "has_villain": {"type": "boolean"}, "villain": {"type": "string"},
    "has_victim": {"type": "boolean"}, "victim": {"type": "string"},
    "has_hero": {"type": "boolean"}, "hero": {"type": "string"},
    "politics": {"type": "boolean"}, "side": {"type": "string", "enum": ['left', 'right', 'both', 'none']},
    **SHAPE_FIELDS},
    "required": ["narrative", "retold", "genre", "motif_chapter", "motif", *SHAPE_FIELDS, "has_villain", "villain", "has_victim",
                 "victim", "has_hero", "hero", "politics", "side"]}
# A narrative counts only if at least this share of its sampled posts are about its claim (telling it or arguing
# over it alike). Oct 4: a group of trans people talking about their own gender was labeled with an anti-trans claim
# one of them had quoted
ABOUT_SHARE = 0.5
ABOUT_PROMPT = """A claim: {claim}

A post: {post}

Is this post about that claim: telling it, repeating it, joking about it or arguing over it? Or is it about \
something else?"""
ABOUT_SCHEMA = {"type": "object", "properties": {"about": {"type": "string", "enum": ["the claim", "something else"]}},
                "required": ["about"]}
WORD = re.compile(r"[a-z0-9']+")
NOISE = re.compile(r'@someone|\[link: [^\]]*\]|(?:[a-z0-9-]+\.)+[a-z]{2,}/\S*')  # the last: links stored before Oct 4

_embedder = None


def embed(texts: list[str]) -> np.ndarray:
    """Unit vectors from mxbai-embed-large on the GPU (through Ollama), as for stories, cached for a few days in a
    file of their own; the static model if Ollama can't."""
    from app.analysis.clustering import ollama_embed
    os.makedirs(FOLDER, exist_ok=True)
    try:
        return ollama_embed(list(texts), cache=os.path.join(FOLDER, 'embeddings.sqlite'), keep_days=4)
    except Exception as e:
        logger.warning("Narrative embeddings from Ollama failed (%s); using %s", type(e).__name__, EMBEDDER)
        global _embedder
        if _embedder is None:
            from model2vec import StaticModel
            _embedder = StaticModel.from_pretrained(EMBEDDER)
        v = np.asarray(_embedder.encode(list(texts)), dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def words(text: str) -> set[str]:
    return set(WORD.findall(NOISE.sub(' ', text.lower())))


def normalized(text: str) -> str:
    return ' '.join(WORD.findall(NOISE.sub(' ', text.lower())))


def load(hours: float) -> list[dict]:
    from app.vernacular import DB
    since = (dt.now(timezone.utc) - td(hours=hours)).isoformat(timespec='seconds')
    con = sqlite3.connect(DB)
    rows = con.execute('SELECT key, author, text, reply, source, links FROM post WHERE collected >= ?',
                       (since,)).fetchall()
    con.close()
    # Feeds and bots post far more than people: an account with more than FEED_POSTS posts in the window is left
    # out, and so is a bare link share (a headline and its link), which is a story being passed on, not told, and a
    # post with hardly any words (emoji and a link: promotion, not talk)
    from app.vernacular import ADULT, english
    per_author = Counter(row[1] for row in rows)
    return [{'key': k, 'author': a, 'text': t, 'reply': r, 'source': s, 'links': json.loads(links or '[]')}
            for k, a, t, r, s, links in rows
            if len(NOISE.sub('', t).strip()) >= MIN_CHARS and len(WORD.findall(NOISE.sub(' ', t.lower()))) >= MIN_WORDS
            and english(t) and not ADULT.search(t) and per_author[a] <= FEED_POSTS * max(1, hours / 6)
            and not ('[link:' in t and len(NOISE.sub('', t).strip()) < 120) and '[BOT]' not in t]


def neighbours(v: np.ndarray, k: int, chunk: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """Each row's k nearest other rows (indices, similarities), by blocks so memory stays small."""
    n = len(v)
    k = max(1, min(k, n - 1))
    idx = np.zeros((n, k), dtype=np.int64)
    sim = np.zeros((n, k), dtype=np.float32)
    for start in range(0, n, chunk):
        block = v[start:start + chunk] @ v.T
        for row in range(block.shape[0]):
            block[row, start + row] = -1  # not its own neighbour
        top = np.argpartition(-block, k, axis=1)[:, :k]
        vals = np.take_along_axis(block, top, axis=1)
        order = np.argsort(-vals, axis=1)
        idx[start:start + chunk] = np.take_along_axis(top, order, axis=1)
        sim[start:start + chunk] = np.take_along_axis(vals, order, axis=1)
    return idx, sim


def groups(posts: list[dict]) -> list[list[int]]:
    """Paraphrase groups: connected components of the mutual-neighbour graph above SIMILARITY."""
    v = embed([p['text'] for p in posts])
    if len(posts) < 2:
        return []
    idx, sim = neighbours(v, NEIGHBOURS)
    near = [set(idx[i][sim[i] >= SIMILARITY]) for i in range(len(posts))]
    parent = list(range(len(posts)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, ns in enumerate(near):
        for j in ns:
            if i in near[j]:
                parent[find(i)] = find(j)
    found = defaultdict(list)
    for i in range(len(posts)):
        found[find(i)].append(i)
    return [g for g in found.values() if len(g) > 1]


def variety(texts: list[str], rng: random.Random) -> float:
    """One minus the mean word overlap (Jaccard) between pairs of versions: 0 the same words, 1 nothing shared."""
    sets = [words(t) for t in texts]
    pairs = [(a, b) for a in range(len(sets)) for b in range(a + 1, len(sets))]
    if not pairs:
        return 0.0
    pairs = rng.sample(pairs, min(len(pairs), 200))
    overlap = [len(sets[a] & sets[b]) / max(1, len(sets[a] | sets[b])) for a, b in pairs]
    return round(1 - float(np.mean(overlap)), 3)


def describe(posts: list[dict], members: list[int], rng: random.Random) -> dict:
    texts = [posts[i]['text'] for i in members]
    authors = len({posts[i]['author'] for i in members})
    exact = Counter(normalized(t) for t in texts).most_common(1)[0][1]
    var = variety(texts, rng)
    kind = 'copypasta' if var < COPY_VARIETY or exact >= 0.5 * len(texts) else \
        'told' if var >= FOLK_VARIETY else 'echoed'
    distinct = list(dict.fromkeys(texts))
    shared = Counter(url for i in members for url in posts[i].get('links') or [])
    return {'members': members, 'posts': len(members), 'authors': authors, 'variety': var, 'kind': kind,
            'shared': shared.most_common(5),
            'replies': round(sum(posts[i]['reply'] for i in members) / len(members), 2),
            'sources': dict(Counter(posts[i]['source'] for i in members)),
            'examples': rng.sample(distinct, min(len(distinct), SAMPLE))}


def label(group: dict, cache: dict) -> dict | None:
    from app.analysis import llm
    shown = sorted(group['examples'])
    key = hashlib.sha1((PROMPT + json.dumps(shown)).encode()).hexdigest()
    if key not in cache:
        answer = llm.complete_json(PROMPT.format(posts='\n'.join(f'- {t[:280]}' for t in shown),
                                                 genres='; '.join(GENRES), chapters='; '.join(MOTIF_CHAPTERS),
                                                 shapes=prompt_fields()),
                                   SCHEMA, max_tokens=600)
        if not answer:
            return None
        settle(answer)  # a conspiracy scope only when a secret plot is claimed
        for part in ('villain', 'victim', 'hero'):  # a part the model says the story lacks stays empty
            if not answer.get(f'has_{part}'):
                answer[part] = ''
        cache[key] = {**answer, 'model': llm.model()}
    return cache[key]


def about(group: dict, claim: str, cache: dict) -> float:
    """The share of the group's sampled posts that are about its claim, asked one post at a time (small models lose
    track of numbered lists)."""
    from app.analysis import llm
    votes = []
    for post in group['examples']:
        key = hashlib.sha1(f'{ABOUT_PROMPT}\n{claim}\n{post}'.encode()).hexdigest()
        if key not in cache:
            answer = llm.complete_json(ABOUT_PROMPT.format(claim=claim, post=post[:400]), ABOUT_SCHEMA, max_tokens=20)
            if not answer:
                continue
            cache[key] = answer['about']
        votes.append(cache[key] == 'the claim')
    return sum(votes) / len(votes) if votes else 0.0


CANDIDATES = 3  # nearest stories or passages the model is asked about
STORY_PROMPT = """People online are retelling this: {claim}
For example: {example}

Today's news stories:
{other}

Is what they're retelling about one of these stories? Answer with the story's number and how:
- "N event": it's about that story's own event, case or person
- "N issue": it's about the same specific issue or controversy (for example a party's vote declaring Zionism racist
  and a singer's Free Palestine shirt: both Israel and Palestine), but not that event. A shared broad topic, a
  shared kind of thing (two different ads, two different crimes) or a shared famous name is not the same issue
- "none": most of the time

reason: briefly
link: "N event", "N issue" or "none"""
VOICE_PROMPT = """People online are retelling this: {claim}
For example: {example}

Passages from recorded focus groups of voters (and the hosts discussing them):
{other}

Which passage, if any, has voters voicing, repeating or arguing about the same claim? Mentioning the same person,
place or topic is not enough. Most of the time the answer is "none".

reason: briefly
passage: the passage's number, or "none"""
VOICE_FLOOR = 0.72  # passages less alike than this (mxbai) aren't offered
CONFIRM_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string"}, "same": {"type": "boolean"}},
                  "required": ["reason", "same"]}


def ask(prompt: str, schema: dict, group: dict, other: str, cache: dict, limit: int = 600) -> dict | None:
    """The model's answer about a cross-check candidate (cached by the question and what it's shown), or None."""
    from app.analysis import llm
    claim = group['label']['narrative'] or group['examples'][0]
    key = hashlib.sha1(json.dumps([prompt, claim, other]).encode()).hexdigest()
    if key not in cache:
        answer = llm.complete_json(prompt.format(claim=claim, example=group['examples'][0][:280],
                                                 other=other[:limit]), schema, max_tokens=120)
        if not answer:
            return None
        cache[key] = {**answer, 'claim': claim, 'other': other[:200]}
    return cache[key]


def confirm(prompt: str, group: dict, other: str, cache: dict) -> bool:
    answer = ask(prompt, CONFIRM_SCHEMA, group, other, cache)
    return bool(answer and answer.get('same'))


def voice(group: dict, candidates: list[dict], cache: dict) -> dict | None:
    """The Focus Group passage the model picks as voicing the same claim, out of the candidates, or None; a forced
    choice with "none" offered, which a small model can't agree its way through the way it does a yes-or-no."""
    if not candidates:
        return None
    options = '\n'.join(f'{n}. "{c["text"][:400]}"' for n, c in enumerate(candidates, 1))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string"},
        "passage": {"type": "string", "enum": [str(n) for n in range(1, len(candidates) + 1)] + ['none']}},
        "required": ["reason", "passage"]}
    answer = ask(VOICE_PROMPT, schema, group, options, cache, limit=2000)
    pick = (answer or {}).get('passage', 'none')
    return candidates[int(pick) - 1] if pick != 'none' else None


def story_link(group: dict, candidates: list[str], cache: dict) -> dict | None:
    """The story the model links the narrative to, as the same event or the same issue, out of the candidates (a
    forced choice with "none" offered), or None."""
    if not candidates:
        return None
    options = '\n'.join(f'{n}. {story}' for n, story in enumerate(candidates, 1))
    links = [f'{n} {how}' for n in range(1, len(candidates) + 1) for how in ('event', 'issue')] + ['none']
    schema = {"type": "object", "properties": {"reason": {"type": "string"},
                                               "link": {"type": "string", "enum": links}},
              "required": ["reason", "link"]}
    answer = ask(STORY_PROMPT, schema, group, options, cache, limit=2000)
    link = (answer or {}).get('link', 'none')
    if link == 'none':
        return None
    number, how = link.split()
    return {'label': candidates[int(number) - 1], 'relation': 'same event' if how == 'event' else 'same issue'}


def rated_leans() -> dict[str, int]:
    """Outlet -> its AllSides lean (-2 left to 2 right), for the outlets AllSides rates."""
    from app.models import Session, Agency
    with Session() as s:
        return {name: bias for name, bias in s.query(Agency.name, Agency._bias).filter(Agency.lean_rated)}  # noqa


def shared_side(shares: list[tuple[str, int]], leans: dict[str, int], least: int = 2) -> str | None:
    """Which side passes the story around, from the rated outlets whose articles its posts share (at least `least`
    shares): 'left', 'right' or 'center', or None without enough to go on. Evidence, unlike the model's guess."""
    rated = [(leans[outlet], n) for outlet, n in shares if outlet in leans]
    total = sum(n for _, n in rated)
    if total < least:
        return None
    mean = sum(lean * n for lean, n in rated) / total
    return 'left' if mean <= -0.5 else 'right' if mean >= 0.5 else 'center'


def articles(urls: list[str]) -> dict[str, dict]:
    """The articles in our own database at these addresses (http or https, with or without www or a trailing slash):
    url -> {title, outlet, story} with the headline it was last seen under and the story it's in, if any."""
    from app.models import Session, Article, Agency, Headline, Story, StoryHeadline
    from urllib.parse import urlsplit
    variants = {}
    for url in urls:
        parts = urlsplit(url)
        host = parts.netloc.removeprefix('www.')
        for scheme in ('https', 'http'):
            for h in (host, 'www.' + host):
                for path in {parts.path, parts.path.rstrip('/'), parts.path.rstrip('/') + '/'}:
                    variants[f'{scheme}://{h}{path}'] = url
    found = {}
    with Session() as s:
        keys = list(variants)
        for start in range(0, len(keys), 500):
            rows = s.query(Article.url, Agency.name, Headline.processed, Story.label).join(Article.agency).join(
                Headline, Headline.article_id == Article.id).outerjoin(
                StoryHeadline, StoryHeadline.headline_id == Headline.id).outerjoin(
                Story, Story.id == StoryHeadline.story_id).filter(Article.url.in_(keys[start:start + 500])).order_by(
                Headline.last_accessed).all()
            for url, outlet, title, story in rows:  # later headlines win: the latest wording
                original = variants[url]
                entry = found.setdefault(original, {'url': original, 'outlet': outlet, 'title': title, 'story': None})
                entry['title'] = title or entry['title']
                entry['story'] = story or entry['story']
    return found


def focus_group_segments(window: int = 3) -> list[dict]:
    """The Focus Group transcripts in short windows of consecutive segments (a few sentences each)."""
    from app.models import Session, SideItem, SideTranscript
    out = []
    with Session() as s:
        rows = s.query(SideItem.title, SideItem.published, SideTranscript.segments).join(
            SideTranscript, SideTranscript.item_id == SideItem.id).filter(SideItem.source == 'focusgroup').all()
    for title, published, segments in rows:
        segs = json.loads(segments or '[]')
        for i in range(0, len(segs), window):
            text = ' '.join(x['text'] for x in segs[i:i + window]).strip()
            if len(text) >= MIN_CHARS:
                out.append({'episode': title, 'date': str(published)[:10], 'at': segs[i]['start'], 'text': text})
    return out


def current_stories(limit: int = 80) -> list[str]:
    from app.models import Session, Story
    with Session() as s:
        return [label for (label,) in s.query(Story.label).filter(Story.label.isnot(None)).order_by(
            Story.last_seen.desc()).limit(limit)]


def story_ids(labels: list[str]) -> dict[str, int]:
    """label -> the id of the latest story with it"""
    from app.models import Session, Story
    with Session() as s:
        return {label: sid for sid, label in s.query(Story.id, Story.label).filter(Story.label.in_(labels))
                .order_by(Story.last_seen)}


def made_today() -> bool:
    """Whether today's nightly report (a day's posts) has been written."""
    for path in glob.glob(os.path.join(FOLDER, f"report-{dt.now().strftime('%Y-%m-%d')}-*.json")):
        if read_json(path, {}).get('hours', 0) >= 24:
            return True
    return False


def report(hours: float = 6) -> dict:
    rng = random.Random(4)
    os.makedirs(FOLDER, exist_ok=True)
    posts = load(hours)
    logger.info("Narratives: %d posts from the last %g hours", len(posts), hours)
    found = [describe(posts, g, rng) for g in groups(posts)]
    found = [g for g in found if g['authors'] >= MIN_AUTHORS]
    found.sort(key=lambda g: -g['authors'])
    cache = read_json(JUDGMENTS, {})
    for g in [g for g in found if g['kind'] != 'copypasta'][:LABEL_TOP]:
        g['label'] = label(g, cache)
        lab = g['label']
        if lab and lab.get('retold') and lab.get('narrative'):
            g['about'] = round(about(g, lab['narrative'], cache), 2)
            if g['about'] < ABOUT_SHARE:  # most posts aren't about it: a topic with one post's claim, not a narrative
                g['label'] = {**lab, 'retold': False, 'misread': True}
    write_json(JUDGMENTS, cache)
    # Cross-checks, by embedding each narrative's claim (or its versions) against voters' words and today's stories
    narratives = [g for g in found if (g.get('label') or {}).get('retold')]
    # The articles their posts share, looked up in our own database: an exact tie to a story, no guessing
    known = articles(sorted({url for g in narratives for url, _ in g['shared']}))
    leans = rated_leans()
    for g in narratives:
        g['shared_side'] = shared_side([(known[url]['outlet'], n) for url, n in g['shared'] if url in known], leans)
        g['articles'] = [{**known[url], 'shares': n} for url, n in g['shared'] if url in known][:3]
        g['outside'] = [{'url': url, 'shares': n} for url, n in g['shared'] if url not in known][:3]
    segments = focus_group_segments()
    stories = current_stories()
    if narratives:
        claims = embed([g['label']['narrative'] or g['examples'][0] for g in narratives])
        centers = np.vstack([embed(g['examples']).mean(axis=0) for g in narratives])
        centers /= np.maximum(np.linalg.norm(centers, axis=1, keepdims=True), 1e-12)
        if segments:
            seg = embed([x['text'] for x in segments])
            sims = np.maximum(claims @ seg.T, centers @ seg.T)
            for g, row in zip(narratives, sims):
                # The closest few passages are only candidates; the model keeps the ones that really voice or argue
                # about the same claim
                candidates = [segments[i] for i in np.argsort(-row)[:CANDIDATES] if row[i] >= VOICE_FLOOR]
                pick = voice(g, candidates, cache)
                g['voters'] = [pick] if pick else []
        if stories:
            st = embed(stories)
            sims = np.maximum(claims @ st.T, centers @ st.T)
            ids = story_ids(stories)
            for g, row in zip(narratives, sims):
                g['story'] = story_link(g, [stories[i] for i in np.argsort(-row)[:CANDIDATES]], cache)
                if g['story']:  # its id too, since labels get reworded (the story pages tie by id, Oct 6)
                    g['story']['id'] = ids.get(g['story']['label'])
        write_json(JUDGMENTS, cache)
        try:
            from app.analysis import factchecks
            checked = factchecks.for_narratives({n: g['label']['narrative'] for n, g in enumerate(narratives)
                                                 if g['label'].get('narrative')})
        except Exception as e:  # noqa: fact-checks are extra; the report stands without them
            logger.warning("Narratives: fact-checks failed (%s)", e)
            checked = {}
        for n, g in enumerate(narratives):
            g['factchecks'] = [{k: c[k] for k in ('source', 'title', 'url', 'published')} for c in checked.get(n, [])]
    out = {'made': dt.now().isoformat(timespec='minutes'), 'hours': hours, 'posts': len(posts),
           'authors': len({p['author'] for p in posts}), 'groups': len(found),
           'kinds': dict(Counter(g['kind'] for g in found)), 'focus_group_segments': len(segments),
           'found': [{k: v for k, v in g.items() if k != 'members'} for g in found]}
    stamp = dt.now().strftime('%Y-%m-%d-%H%M')
    write_json(os.path.join(FOLDER, f'report-{stamp}.json'), out, indent=1)
    with open(os.path.join(FOLDER, f'report-{stamp}.md'), 'w') as f:
        f.write(markdown(out))
    logger.info("Narratives: %d groups (%s), %d labeled retold narratives; report-%s", len(found), out['kinds'],
                len(narratives), stamp)
    return out


def markdown(out: dict) -> str:
    lines = [f"# Narratives ({out['made']}, last {out['hours']:g} hours)", '',
             f"{out['posts']} posts from {out['authors']} accounts; {out['groups']} groups of 5+ people: "
             f"{out['kinds']}. Focus Group segments checked: {out['focus_group_segments']}.", '']
    told = [g for g in out['found'] if (g.get('label') or {}).get('retold')]
    lines += ['## Retold narratives', '']
    for g in told:
        lab = g['label']
        roles = ', '.join(f'{r}: {lab[r]}' for r in ('villain', 'victim', 'hero') if lab.get(r))
        lines.append(f"### {lab['narrative']}")
        lines.append(f"{g['authors']} people, {g['posts']} posts, wording variety {g['variety']} ({g['kind']}); "
                     f"{lab['genre']}; motif {lab['motif_chapter']}: {lab['motif'] or '-'}; "
                     f"politics: {lab['politics']} ({lab['side']}){'; ' + roles if roles else ''}")
        for a in g.get('articles') or []:
            lines.append(f"Sharing ({a['shares']}x): {a['title']} ({a['outlet']}) {a['url']}"
                         + (f" [story: {a['story']}]" if a['story'] else ''))
        story = g.get('story')
        if story and story['relation'] == 'same event':
            lines.append(f"In the news: {story['label']}")
        elif story:
            lines.append(f"Related story (same issue): {story['label']}")
        else:
            lines.append('In the news: no matching or related story today')
        for c in g.get('factchecks') or []:
            lines.append(f"Fact-checked ({c['source']}, {c['published'][:10]}): {c['title']} {c['url']}")
        if g.get('voters'):
            for v in g['voters']:
                lines.append(f"Voters say it too (The Focus Group, {v['date']}): \"{v['text'][:240]}\"")
        else:
            lines.append('Voters: not raised in the Focus Group transcripts')
        lines += ['Versions:'] + [f'- {t[:200]}' for t in g['examples'][:5]] + ['']
    copies = [g for g in out['found'] if g['kind'] == 'copypasta']
    lines += ['## Copypasta (same words, many accounts)', '']
    lines += [f"- {g['authors']} accounts, {g['posts']} posts: {g['examples'][0][:160]}" for g in copies[:30]]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=float, default=6)
    report(parser.parse_args().hours)
