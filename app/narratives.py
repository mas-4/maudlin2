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
4. Cross-checks: the Focus Group transcripts (do voters say it in their own words?) and today's news stories (which
   story it rides on, if any). The nearest few by embedding are only candidates: the model, shown both side by side,
   says whether a story is the same event or the same issue (anything looser isn't shown), and whether voters voice
   the same claim; otherwise the report says there's none.

Writes a report to data/narratives/ (JSON and Markdown); nothing here is published. Run:
    .venv/bin/python -m app.narratives [--hours 6]
"""
import argparse
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

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
JUDGMENTS = os.path.join(FOLDER, 'judgments.json')
EMBEDDER = 'minishlab/potion-base-32M'
SIMILARITY = 0.78  # mutual neighbours this alike (mxbai) are versions of one thing
NEIGHBOURS = 15
MIN_AUTHORS = 5
MIN_CHARS = 40
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
news. Answer in the fields below.

narrative: the shared claim or story in one plain sentence, or "" if there is none
retold: true if they retell one narrative, false if they only share a topic
genre: one of {genres}
motif_chapter: the chapter of Thompson's Motif-Index it fits best, one of {chapters}
motif: the specific motif in a few words (for example "the poisoned well", "the stranger who steals children",
"the hidden ruler"), or ""
villain: who is cast as the villain, or ""
victim: who is cast as the victim, or ""
hero: who is cast as the hero or rescuer, or ""
politics: true if it is about politics or public life
side: "left", "right", "both" or "none" (whose politics it carries)"""
SCHEMA = {"type": "object", "properties": {
    "narrative": {"type": "string"}, "retold": {"type": "boolean"}, "genre": {"type": "string", "enum": GENRES},
    "motif_chapter": {"type": "string", "enum": MOTIF_CHAPTERS}, "motif": {"type": "string"},
    "villain": {"type": "string"}, "victim": {"type": "string"}, "hero": {"type": "string"},
    "politics": {"type": "boolean"}, "side": {"type": "string", "enum": ['left', 'right', 'both', 'none']}},
    "required": ["narrative", "retold", "genre", "motif_chapter", "motif", "villain", "victim", "hero", "politics",
                 "side"]}
WORD = re.compile(r"[a-z0-9']+")
NOISE = re.compile(r'@someone|\[link: [^\]]*\]')

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
    rows = con.execute('SELECT key, author, text, reply, source FROM post WHERE collected >= ?', (since,)).fetchall()
    con.close()
    # Feeds and bots post far more than people: an account with more than FEED_POSTS posts in the window is left
    # out, and so is a bare link share (a headline and its link), which is a story being passed on, not told
    from app.vernacular import ADULT, english
    per_author = Counter(a for _, a, _, _, _ in rows)
    return [{'key': k, 'author': a, 'text': t, 'reply': r, 'source': s} for k, a, t, r, s in rows
            if len(NOISE.sub('', t).strip()) >= MIN_CHARS and english(t) and not ADULT.search(t) and per_author[a] <= FEED_POSTS * max(1, hours / 6)
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
    return {'members': members, 'posts': len(members), 'authors': authors, 'variety': var, 'kind': kind,
            'replies': round(sum(posts[i]['reply'] for i in members) / len(members), 2),
            'sources': dict(Counter(posts[i]['source'] for i in members)),
            'examples': rng.sample(distinct, min(len(distinct), SAMPLE))}


def label(group: dict, cache: dict) -> dict | None:
    from app.analysis import llm
    shown = sorted(group['examples'])
    key = hashlib.sha1(json.dumps(shown).encode()).hexdigest()
    if key not in cache:
        answer = llm.complete_json(PROMPT.format(posts='\n'.join(f'- {t[:280]}' for t in shown),
                                                 genres='; '.join(GENRES), chapters='; '.join(MOTIF_CHAPTERS)),
                                   SCHEMA, max_tokens=400)
        if not answer:
            return None
        cache[key] = {**answer, 'model': llm.model()}
    return cache[key]


CANDIDATES = 3  # nearest stories or passages the model is asked about
STORY_PROMPT = """People online are retelling this: {claim}
For example: {example}

News story: {other}

How does what they're retelling relate to this news story?
- "same event": it's about this story's event, case or person
- "same issue": it's about the same issue or controversy (for example a party's vote on Zionism and a singer's
  Free Palestine shirt are both about Israel and Palestine), but not this event
- "unrelated": anything looser, like the same broad topic

reason: briefly
relation: same event, same issue or unrelated"""
STORY_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string"},
                                                 "relation": {"type": "string",
                                                              "enum": ['same event', 'same issue', 'unrelated']}},
                "required": ["reason", "relation"]}
VOICE_PROMPT = """People online are retelling this: {claim}
For example: {example}

Words from a recorded focus group of voters:
"{other}"

Do these voters voice, repeat or argue about the same claim (not merely mention the same person or topic)?

reason: briefly
same: true or false"""
CONFIRM_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string"}, "same": {"type": "boolean"}},
                  "required": ["reason", "same"]}


def ask(prompt: str, schema: dict, group: dict, other: str, cache: dict) -> dict | None:
    """The model's answer about one cross-check candidate (cached), or None without one."""
    from app.analysis import llm
    claim = group['label']['narrative'] or group['examples'][0]
    key = hashlib.sha1(json.dumps([prompt[:40], claim, other]).encode()).hexdigest()
    if key not in cache:
        answer = llm.complete_json(prompt.format(claim=claim, example=group['examples'][0][:280], other=other[:600]),
                                   schema, max_tokens=120)
        if not answer:
            return None
        cache[key] = {**answer, 'claim': claim, 'other': other[:200]}
    return cache[key]


def confirm(prompt: str, group: dict, other: str, cache: dict) -> bool:
    answer = ask(prompt, CONFIRM_SCHEMA, group, other, cache)
    return bool(answer and answer.get('same'))


def story_link(group: dict, candidates: list[str], cache: dict) -> dict | None:
    """The first candidate story the model calls the same event, else the first it calls the same issue."""
    answers = [(story, (ask(STORY_PROMPT, STORY_SCHEMA, group, story, cache) or {}).get('relation'))
               for story in candidates]
    for wanted in ('same event', 'same issue'):
        match = next((story for story, relation in answers if relation == wanted), None)
        if match:
            return {'label': match, 'relation': wanted}
    return None


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


def report(hours: float = 6) -> dict:
    rng = random.Random(4)
    os.makedirs(FOLDER, exist_ok=True)
    posts = load(hours)
    logger.info("Narratives: %d posts from the last %g hours", len(posts), hours)
    found = [describe(posts, g, rng) for g in groups(posts)]
    found = [g for g in found if g['authors'] >= MIN_AUTHORS]
    found.sort(key=lambda g: -g['authors'])
    try:
        with open(JUDGMENTS) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    for g in [g for g in found if g['kind'] != 'copypasta'][:LABEL_TOP]:
        g['label'] = label(g, cache)
    with open(JUDGMENTS, 'w') as f:
        json.dump(cache, f)
    # Cross-checks, by embedding each narrative's claim (or its versions) against voters' words and today's stories
    narratives = [g for g in found if (g.get('label') or {}).get('retold')]
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
                candidates = [segments[i] for i in np.argsort(-row)[:CANDIDATES]]
                g['voters'] = [c for c in candidates if confirm(VOICE_PROMPT, g, c['text'], cache)][:2]
        if stories:
            st = embed(stories)
            sims = np.maximum(claims @ st.T, centers @ st.T)
            for g, row in zip(narratives, sims):
                g['story'] = story_link(g, [stories[i] for i in np.argsort(-row)[:CANDIDATES]], cache)
        with open(JUDGMENTS, 'w') as f:
            json.dump(cache, f)
    out = {'made': dt.now().isoformat(timespec='minutes'), 'hours': hours, 'posts': len(posts),
           'authors': len({p['author'] for p in posts}), 'groups': len(found),
           'kinds': dict(Counter(g['kind'] for g in found)), 'focus_group_segments': len(segments),
           'found': [{k: v for k, v in g.items() if k != 'members'} for g in found]}
    stamp = dt.now().strftime('%Y-%m-%d-%H%M')
    with open(os.path.join(FOLDER, f'report-{stamp}.json'), 'w') as f:
        json.dump(out, f, indent=1)
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
        story = g.get('story')
        if story and story['relation'] == 'same event':
            lines.append(f"In the news: {story['label']}")
        elif story:
            lines.append(f"Related story (same issue): {story['label']}")
        else:
            lines.append('In the news: no matching or related story today')
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
