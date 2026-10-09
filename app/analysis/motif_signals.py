"""Many ways of telling which motifs a claim belongs to (Oct 8; the person made filing claims the project's first
priority). Until today one embedding model's likenesses found the candidates and one model picked among them; when
that one way of seeing missed, nothing else caught it. Each signal here reads a (claim, motif) pair differently:

  keywords   BM25 over the motif's note, name and claims: the distinctive words embeddings blur ("Hatch Act")
  note       the claim against the motif's scope note alone, by meaning (the names are often playful nicknames; the
             note says what the motif covers)
  shape      the claim restated by the filing model as the bare shape of its story (no names, places or dates),
             against the note
  votes      the filed claims most like this one, each voting for its motifs (nearest neighbours)
  nomic      a second embedding model (nomic-embed-text) against the motif's description and its nearest claim, so
             two models' blind spots can cover each other
  news out   the claim against each note and each motif's nearest claim with the day's news taken out: the main
             directions the latest headlines vary along (mostly topic: Iran, Texas, a storm) projected away, so what's
             left leans to framing (experiment E1, Oct 8: +1.3 points of the person's motifs in the top 12)
  layers     the claim described by the filing model layer by layer in generic words (a character type, a plot, a
             theory, an argument, a value at stake), each layer against every motif's note: the best layer, and the
             layer that goes with the motif's genre (experiment E7, Oct 8: +1.4 points of the person's motifs in the
             top 12, 17 of 76 hard misses back; it reads a claim the way the person does)
  group      the claim against the person's groups (each the center of its motifs' claims), a motif scored by its best
             group: a group pools many small motifs' evidence (Oct 8, the person: route through groups; one route among
             the others, not a tree: an ungrouped motif scores nothing here and is found the other ways)
  rerank     a cross-encoder (Qwen3-Reranker-0.6B) reading the claim and the motif together, yes or no
  judge      the filing model asked, of this one pair, is the claim an instance of the motif; its probability of yes

The cheap ones are worked out against every motif (to find candidates); rerank and judge only for a shortlist. With
leave_out the claim is taken out of its own motifs first, so a claim already filed is tested as if it were new.
motif_combiner.py weighs them."""
import hashlib
import json
import math
import os
import re
import time
from collections import Counter

import numpy as np

from app.analysis import motif_index as mi
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'motifs')
SHAPES = os.path.join(FOLDER, 'claim_shapes.json')  # claim key -> its bare shape, by the filing model
RERANKS = os.path.join(FOLDER, 'rerank_cache.json')  # pair hash -> the reranker's P(yes)
JUDGED = os.path.join(FOLDER, 'pair_judge_cache.json')
ELEMENTS = os.path.join(FOLDER, 'motif_elements.json')  # motif id -> {'element': its must-have, 'from': what it was drafted from}
LAYERED = os.path.join(FOLDER, 'claim_layers.json')  # claim key -> {layer: its generic sentence or 'none'}  # pair hash -> the filing model's P(yes)
NOMIC = 'nomic-embed-text'
RERANKER = 'Qwen/Qwen3-Reranker-0.6B'
JUDGE_MODEL = 'gemma4:26b'
# The yes or no on a (claim, motif) pair, for the confidence model: Bespoke Labs' Nimble 9B, a decision model (one pass,
# a probability, no text; Ollama's /v1/systemone), since Oct 9: on the person's 817 decided filings it judged as well
# as Gemma 26B (AUC 0.824 alone, 0.895 in the confidence model, against 0.818 and 0.894) at 0.22 s a pair (J1 in
# docs/filing-experiments.md; its 8-bit build is 9.5 GB, a little of it on the CPU: the 4-bit one that fits whole judged
# worse, 0.797 against 0.818). None: Gemma 26B's yes or no (JUDGE_PROMPT) as before
JUDGE_DECIDER = 'nimble:9b'
JUDGE_QUESTION = ('Is the new claim an instance of this motif: the same shape of story, as its tellers tell it, as the '
                  'claims filed under it, not just the same topic, person or word?')
# Each motif's must-have element, drafted by Gemma 26B from its name, genre and note (not its claims), and shown to the
# judge with a question that asks for it (J2, Oct 9: the casebook's lesson that the person checks what a motif needs;
# on the person's Oct 9 rulings the judge went from AUC 0.54 to 0.79, and 0.811 against 0.801 on every decision).
# Drafted again when the name, genre or note changes; a motif without one yet is judged the old way meanwhile
JUDGE_ELEMENTS = True
ELEMENT_LINE = 'What a telling must contain to be this motif:'
ELEMENT_QUESTION = 'Does the new claim, as told, contain what a telling must contain to be this motif? ' + JUDGE_QUESTION
ELEMENT_PROMPT = """A motif in our index of recurring story shapes in what people tell about politics and public life:
Name: {name}
Genre: {genre}
What it covers: {note}

In one sentence: what must a telling contain to be an instance of this motif, the part without which it would be a \
different motif or none? Not its topic, people or place: the element itself (for "Passing the buck": something has \
gone wrong and the one responsible deflects the blame onto others)."""
ELEMENT_SCHEMA = {"type": "object", "properties": {"element": {"type": "string", "maxLength": 300}}, "required": ["element"]}
NEIGHBOURS = 15
NEWS = os.path.join(FOLDER, 'news_directions.npz')  # the latest headlines' center and main directions, a day at a time
NEWS_HEADLINES = 6000
NEWS_DIRECTIONS = 40
NEWS_EVERY = 86400  # seconds
STOP = {'a', 'an', 'the', 'and', 'or', 'but', 'if', 'of', 'to', 'in', 'on', 'at', 'by', 'for', 'with', 'from', 'as',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'it', 'its', 'this', 'that', 'these', 'those', 'he',
        'she', 'they', 'them', 'his', 'her', 'their', 'we', 'our', 'you', 'your', 'i', 'me', 'my', 'not', 'no', 'so',
        'than', 'then', 'there', 'here', 'what', 'which', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how',
        'all', 'any', 'some', 'more', 'most', 'other', 'such', 'only', 'own', 'same', 'too', 'very', 'can', 'will',
        'just', 'should', 'now', 'says', 'said', 'say', 'about', 'into', 'over', 'after', 'before', 'also', 'has',
        'have', 'had', 'do', 'does', 'did', 'would', 'could', 'may', 'might', 'must', 'one', 'two', 'new', 'people'}
WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
# More embedders (E11, Oct 9: of twelve tried, Qwen3-Embedding 8B with Snowflake Arctic Embed 2 lifted the shortlist's
# top 12 from 82.3% to 85.2%): each the claim against each motif's name and note, and against its nearest claim. Its
# query and document prefixes, as its model card says
EMBEDDERS = {
    'qwen3 8b': ('qwen3-embedding:8b', 'Instruct: Given a claim people tell about politics or public life, find the '
                 'recurring story motif it is an instance of\nQuery: ', ''),
    'arctic2': ('snowflake-arctic-embed2', 'query: ', ''),
}
CHEAP = ['keywords', 'note', 'shape', 'votes', 'nomic desc', 'nomic near', 'group', 'news out note', 'news out near',
         'layers best', 'layer of its genre'] + [f'{k} {x}' for k in EMBEDDERS for x in ('note', 'near')]

SHAPE_PROMPT = """A claim people are telling or arguing over:
{claim}

Restate it as the bare shape of the story it tells, in one plain sentence: what its tellers say is true, with kinds of \
people, places and things in place of particular ones ("a party leader", "immigrants", "a foreign power"), and no \
names or dates. Keep what makes it this story and not another."""
LAYERS_PROMPT = """A claim people are telling or arguing over:
{claim}

Describe the story it tells layer by layer, each in one plain generic sentence with kinds of people, places and things \
instead of names and dates, or "none" if it doesn't have that layer:
character: the type of person or group at the center, as its tellers see them
plot: the sequence of events it says happened or will happen
theory: the hidden cause or belief about how things work that it rests on
argument: the case it makes, or the move it makes against the other side
value: the value it says is at stake or betrayed"""
LAYER_NAMES = ['character', 'plot', 'theory', 'argument', 'value']
LAYERS_SCHEMA = {"type": "object", "properties": {n: {"type": "string", "maxLength": 240} for n in LAYER_NAMES},
                 "required": LAYER_NAMES}
GENRE_LAYER = {'Archetypes': 'character', 'Plots': 'plot', 'Theories': 'theory', 'Beliefs': 'theory',
               'Arguments': 'argument', 'Values': 'value', 'Exhortations': 'value'}
SHAPE_SCHEMA = {"type": "object", "properties": {"shape": {"type": "string", "maxLength": 300}}, "required": ["shape"]}

JUDGE_PROMPT = """Our motif index files claims people make about politics and public life under motifs: recurring shapes of \
story, named as reusable framings, so the same story told about other people or another year lands in the same motif.

Motif: {name}
What it covers: {note}
Some claims filed under it:
{examples}

Claim: {claim}

Is this claim an instance of this motif: the same shape of story, as its tellers tell it, not just the same topic, \
person or word? Answer yes or no."""

RERANK_TASK = ('Given a claim people tell about politics or public life, judge whether it is an instance of this recurring '
               'story motif: the same shape of story as the motif\'s description, not just the same topic, person or word')


def tokens(text: str) -> list[str]:
    out = []
    for w in WORD.findall((text or '').lower().replace('’', "'")):
        w = w.split("'")[0]
        if len(w) > 2 and w not in STOP:
            out.append(w[:-1] if len(w) > 4 and w.endswith('s') and not w.endswith('ss') else w)
    return out


def pair_hash(*parts: str) -> str:
    return hashlib.sha1('\n'.join(parts).encode()).hexdigest()[:16]


def _judge_one(text: str) -> float:
    """One pair's P(yes): from the decision model (its state: the motif and the new claim; asked for the motif's
    element when the state gives one), or Gemma's first word"""
    import requests as rq
    from app.analysis.llm import OLLAMA_URL
    if JUDGE_DECIDER:
        question = ELEMENT_QUESTION if f'\n{ELEMENT_LINE} ' in text else JUDGE_QUESTION
        r = rq.post(f'{OLLAMA_URL}/v1/systemone', timeout=300, json={
            'model': JUDGE_DECIDER, 'state': text, 'questions': {'fits': {'type': 'noul', 'instructions': question}}})
        r.raise_for_status()
        a = r.json()['answers']['fits']
        return round(float(a.get('noul', a.get('probability')) if isinstance(a, dict) else a), 5)
    r = rq.post(f'{OLLAMA_URL}/api/chat', timeout=300, json={
        'model': JUDGE_MODEL, 'messages': [{'role': 'user', 'content': text}], 'think': False,
        'stream': False, 'logprobs': True, 'top_logprobs': 10, 'options': {'temperature': 0, 'num_predict': 1}})
    r.raise_for_status()
    y = no = -math.inf
    for t in ((r.json().get('logprobs') or [{}])[0].get('top_logprobs') or []):
        w = t['token'].strip().lower()
        if w.startswith('yes'):
            y = max(y, t['logprob'])
        elif w.startswith('no'):
            no = max(no, t['logprob'])
    return 0.5 if y == no == -math.inf else (1.0 if no == -math.inf else 0.0 if y == -math.inf
                                             else round(1 / (1 + math.exp(no - y)), 5))


def judge_tag() -> str:
    """Which judge the cached yes-or-no answers and the confidence model's 'judge' signal come from"""
    return (JUDGE_DECIDER + ('+element' if JUDGE_ELEMENTS else '')) if JUDGE_DECIDER else JUDGE_MODEL


def rerank_text(claim: str, doc: str) -> str:
    """The reranker's input for a pair (Qwen3-Reranker's own template)"""
    return ('<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct '
            'provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
            f'<Instruct>: {RERANK_TASK}\n<Query>: {claim}\n<Document>: {doc}'
            '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')


def latest_headlines(n: int = NEWS_HEADLINES) -> list[str]:
    import sqlite3
    con = sqlite3.connect(f'file:{Config.connection_string.removeprefix("sqlite:///")}?mode=ro', uri=True)
    try:
        return [r[0] for r in con.execute('SELECT DISTINCT title FROM headline WHERE title IS NOT NULL '
                                          'ORDER BY last_accessed DESC LIMIT ?', (n,))]
    finally:
        con.close()


def news_directions(vec, headlines=latest_headlines, path: str = NEWS) -> tuple[np.ndarray, np.ndarray] | None:
    """The latest headlines' center and their NEWS_DIRECTIONS main directions (principal components), kept a day;
    None without headlines"""
    import time
    try:
        if time.time() - os.path.getmtime(path) < NEWS_EVERY:
            d = np.load(path)
            return d['center'], d['directions']
    except (OSError, ValueError, KeyError):
        pass
    try:
        titles = headlines()
    except Exception as e:  # noqa: BLE001 - no news out today: the signal stays flat
        logger.warning("News directions: no headlines (%s)", e)
        return None
    if len(titles) <= NEWS_DIRECTIONS:
        return None
    H = np.asarray(vec(titles), dtype=np.float64)
    center = H.mean(0)
    directions = np.linalg.svd(H - center, full_matrices=False)[2][:NEWS_DIRECTIONS]
    np.savez(path + '.tmp.npz', center=center, directions=directions)
    os.replace(path + '.tmp.npz', path)
    return center, directions


def news_out(V: np.ndarray, basis: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Vectors with the news's main directions taken out, back to unit length"""
    center, U = basis
    W = (V - center) - ((V - center) @ U.T) @ U
    return W / np.maximum(np.linalg.norm(W, axis=-1, keepdims=True), 1e-12)


class Signals:
    """The signals for claims against one index's live motifs (those with claims). vec: motif_retriever.Vectors"""

    def __init__(self, index: dict, vec=None):
        from app.analysis import motif_retriever as mr
        self.index = index
        self.vec = vec or mr.Vectors()
        self.entries = [e for e in mi.live(index) if e['claims']]
        self.at = {e['id']: n for n, e in enumerate(self.entries)}
        # keywords: each motif one document (name, note, claims), its words counted per claim so one can be taken out
        self.claim_words = {}
        self.doc = []
        for e in self.entries:
            c = Counter(tokens(e['name']) + tokens(e.get('note') or ''))
            for x in e['claims']:
                k = mi.key(x['claim'])
                self.claim_words.setdefault(k, Counter(tokens(x['claim'])))
                c.update(self.claim_words[k])
            self.doc.append(c)
        self.df = Counter(w for d in self.doc for w in d)
        self.avg = np.mean([sum(d.values()) for d in self.doc]) if self.doc else 1.0
        # every filed claim once, with the motifs it's in (neighbour votes)
        self.filed = {}
        for n, e in enumerate(self.entries):
            for x in e['claims']:
                self.filed.setdefault(mi.key(x['claim']), [x['claim'], set()])[1].add(n)
        self.filed_keys = list(self.filed)
        self._filed_v = None
        self._note_v = None
        self.shapes = read_json(SHAPES, {})
        self.layered = read_json(LAYERED, {})
        self.reranks = read_json(RERANKS, {})
        self.judged = read_json(JUDGED, {})
        self.elements = read_json(ELEMENTS, {})
        self._reranker = None
        from app.analysis import reranker_teach
        self.rerank_tag = reranker_teach.tag()  # its scores are cached per reranker: base, or the taught one's date
        self._news = None  # (center, directions), or False when there's none

    # ---- cheap signals, against every motif ----

    def keywords(self, claim: str, leave_out: bool) -> np.ndarray:
        q = Counter(tokens(claim))
        k = mi.key(claim)
        own = self.claim_words.get(k, Counter()) if leave_out else Counter()
        n_docs = len(self.doc)
        out = np.zeros(n_docs)
        for i, d in enumerate(self.doc):
            inside = leave_out and k in self.filed and i in self.filed[k][1]
            size = sum(d.values()) - (sum(own.values()) if inside else 0)
            for w in q:
                tf = d.get(w, 0) - (own.get(w, 0) if inside else 0)
                if tf <= 0:
                    continue
                df = self.df[w] - (1 if inside and own.get(w) and d.get(w, 0) == own.get(w) else 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                out[i] += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * size / self.avg))
        return out

    def note_vectors(self) -> np.ndarray:
        if self._note_v is None:
            self._note_v = self.vec([e.get('note') or e['name'] for e in self.entries])
        return self._note_v

    def note(self, claim: str) -> np.ndarray:
        return self.note_vectors() @ self.vec([claim])[0]

    def shape_of(self, claim: str, ask: bool = True) -> str | None:
        k = mi.key(claim)
        if k not in self.shapes and ask:
            from app.analysis import llm
            a = llm.complete_json(SHAPE_PROMPT.format(claim=claim), SHAPE_SCHEMA, max_tokens=200, model=JUDGE_MODEL)
            if a and a.get('shape'):
                self.shapes[k] = ' '.join(a['shape'].split())
        return self.shapes.get(k)

    def shape(self, claim: str, ask: bool = True) -> np.ndarray:
        s = self.shape_of(claim, ask)
        return self.note_vectors() @ self.vec([s])[0] if s else np.zeros(len(self.entries))

    def layers_of(self, claim: str, ask: bool = True) -> dict:
        """The claim's layers (LAYER_NAMES), each a generic sentence, those it lacks left out"""
        k = mi.key(claim)
        if k not in self.layered and ask:
            from app.analysis import llm
            a = llm.complete_json(LAYERS_PROMPT.format(claim=claim), LAYERS_SCHEMA, max_tokens=600, model=JUDGE_MODEL)
            if a:
                self.layered[k] = {n: ' '.join(str(a.get(n) or 'none').split()) for n in LAYER_NAMES}
        return {n: t for n, t in (self.layered.get(k) or {}).items() if t and t.strip().lower().rstrip('.') != 'none'}

    def layers(self, claim: str, ask: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Against every motif's note: the claim's best layer, and the layer that goes with the motif's genre (-1
        where it has none)"""
        n = len(self.entries)
        ls = self.layers_of(claim, ask)
        if not ls:
            return np.full(n, -1.0), np.full(n, -1.0)
        sims = dict(zip(ls, self.vec(list(ls.values())) @ self.note_vectors().T))
        best = np.max(np.stack(list(sims.values())), 0)
        if getattr(self, '_genre_layer', None) is None:
            self._genre_layer = [GENRE_LAYER.get(mi.genre_of(e) or '') for e in self.entries]
        of_genre = np.array([sims[g][i] if g in sims else -1.0 for i, g in enumerate(self._genre_layer)])
        return best, of_genre

    def votes(self, claim: str, leave_out: bool) -> np.ndarray:
        if self._filed_v is None:
            self._filed_v = self.vec([self.filed[k][0] for k in self.filed_keys])
        k = mi.key(claim)
        sims = self._filed_v @ self.vec([claim])[0]
        out = np.zeros(len(self.entries))
        order = [i for i in np.argsort(-sims) if not (leave_out and self.filed_keys[i] == k)][:NEIGHBOURS]
        for i in order:
            for m in self.filed[self.filed_keys[i]][1]:
                out[m] += max(float(sims[i]), 0.0) ** 4
        total = out.sum()
        return out / total if total else out

    def _nomic(self, texts: list[str], kind: str) -> np.ndarray:
        from app.analysis.clustering import ollama_embed
        from app.narratives import FOLDER as NFOLDER
        return ollama_embed([f'{kind}: {t}' for t in texts], model=NOMIC, cache=os.path.join(NFOLDER, 'embeddings.sqlite'),
                            keep_days=30)

    def nomic(self, claim: str, leave_out: bool) -> tuple[np.ndarray, np.ndarray]:
        if getattr(self, '_nomic_desc', None) is None:
            self._nomic_desc = self._nomic([mi.described(e) for e in self.entries], 'search_document')
            self._nomic_filed = self._nomic([self.filed[k][0] for k in self.filed_keys], 'search_document')
            self._members = [[] for _ in self.entries]
            for i, k in enumerate(self.filed_keys):
                for m in self.filed[k][1]:
                    self._members[m].append(i)
        q = self._nomic([claim], 'search_query')[0]
        sims = self._nomic_filed @ q
        k = mi.key(claim)
        skip = self.filed_keys.index(k) if leave_out and k in self.filed else -1
        near = np.array([max((sims[i] for i in rows if i != skip), default=-1.0) for rows in self._members])
        return self._nomic_desc @ q, near

    def group(self, claim: str, leave_out: bool) -> np.ndarray:
        """Each motif's best group for the claim: how alike the claim is to the center of the group's claims (the
        claim itself left out), -1 for a motif in no group"""
        if self._filed_v is None:
            self._filed_v = self.vec([self.filed[k][0] for k in self.filed_keys])
        if getattr(self, '_groups', None) is None:
            self._groups = {}
            for n, e in enumerate(self.entries):
                for g in mi.person_groups(e):  # the model's drafted groups aren't evidence
                    self._groups.setdefault(g, set()).add(n)
        k = mi.key(claim)
        q = self.vec([claim])[0]
        best = np.full(len(self.entries), -1.0)
        for members in self._groups.values():
            rows = [i for i, fk in enumerate(self.filed_keys) if self.filed[fk][1] & members and not (leave_out and fk == k)]
            if not rows:
                continue
            c = self._filed_v[rows].mean(0)
            sim = float(c @ q / (np.linalg.norm(c) + 1e-9))
            for n in members:
                best[n] = max(best[n], sim)
        return best

    def news(self, claim: str, leave_out: bool) -> tuple[np.ndarray, np.ndarray]:
        """The claim against each note and each motif's nearest claim (itself held out), the news taken out of all"""
        n = len(self.entries)
        if self._news is None:
            self._news = news_directions(self.vec) or False
        if self._news and getattr(self, '_news_filed', None) is None:
            if self._filed_v is None:
                self._filed_v = self.vec([self.filed[k][0] for k in self.filed_keys])
            self._news_notes = news_out(self.note_vectors(), self._news)
            self._news_filed = news_out(self._filed_v, self._news)
            self._news_members = [[] for _ in self.entries]
            for i, k in enumerate(self.filed_keys):
                for m in self.filed[k][1]:
                    self._news_members[m].append(i)
        if not self._news:
            return np.zeros(n), np.zeros(n)
        q = news_out(self.vec([claim])[0], self._news)
        sims = self._news_filed @ q
        k = mi.key(claim)
        skip = self.filed_keys.index(k) if leave_out and k in self.filed else -1
        near = np.array([max((sims[i] for i in rows if i != skip), default=-1.0) for rows in self._news_members])
        return self._news_notes @ q, near

    def prepare(self, claims: list[str], ask: bool = True, budget: float | None = None):
        """Do the models' part for many claims at once, a model at a time: the shape rewrites (the filing model), then
        every embedding in two batches. Claim by claim, Ollama swapped three models through the GPU for each one
        (Oct 8: about 13 s a claim); after this, cheap() reads caches. With `budget`, the questions not begun by then
        wait for the next run (Oct 8: a newly trained model's first scoring overran its budget by four minutes here)"""
        import time
        t0 = time.time()
        if ask:  # the filing model's questions, PARALLEL at once (llm.parallel), each claim's two in turn
            from app.analysis import llm
            llm.parallel(lambda c: (self.shape_of(c, True), self.layers_of(c, True)), list(dict.fromkeys(claims)),
                         budget=budget)
            self.save()
        t1 = time.time()
        shapes = [self.shapes[mi.key(c)] for c in claims if mi.key(c) in self.shapes]
        layers = [t for c in claims for t in self.layers_of(c, False).values()]
        self.vec(list(dict.fromkeys(list(claims) + shapes + layers)))
        self.note_vectors()
        if self._filed_v is None:
            self._filed_v = self.vec([self.filed[k][0] for k in self.filed_keys])
        if claims:
            self.nomic(claims[0], False)  # the motif side, once
            self._nomic(list(dict.fromkeys(claims)), 'search_query')
            self.embedders(claims[0], False)  # each embedder: the motif side once, then every claim in one call
            for key in EMBEDDERS:
                self._embed(key, list(dict.fromkeys(claims)), True)
            self.news(claims[0], False)  # the headlines, once
        self.timings = {'ask': t1 - t0, 'embed': time.time() - t1}  # seconds, for the run's log

    def cheap(self, claim: str, leave_out: bool = False, ask: bool = True) -> dict[str, np.ndarray]:
        """Every cheap signal against every motif"""
        desc, near = self.nomic(claim, leave_out)
        news_note, news_near = self.news(claim, leave_out)
        best, of_genre = self.layers(claim, ask)
        return {'news out note': news_note, 'news out near': news_near, 'layers best': best, 'layer of its genre': of_genre,'keywords': self.keywords(claim, leave_out), 'note': self.note(claim), 'shape': self.shape(claim, ask),
                'votes': self.votes(claim, leave_out), 'nomic desc': desc, 'nomic near': near,
                'group': self.group(claim, leave_out), **self.embedders(claim, leave_out)}

    def _embed(self, key: str, texts: list[str], query: bool) -> np.ndarray:
        from app.analysis.clustering import ollama_embed
        from app.narratives import FOLDER as NFOLDER
        model, qp, dp = EMBEDDERS[key]
        # the 8B is slow on the CPU: any batch worth it goes to the GPU (BULK there is for the small embedders)
        return ollama_embed([(qp if query else dp) + t for t in texts], model=model, keep_days=30, bulk=50,
                            cache=os.path.join(NFOLDER, 'embeddings.sqlite'))

    def embedders(self, claim: str, leave_out: bool) -> dict[str, np.ndarray]:
        """EMBEDDERS' signals: the claim against each motif's name and note, and against its nearest claim (itself
        held out, -1 for a motif with none)"""
        if getattr(self, '_emb', None) is None:
            self._emb = {}
            for key in EMBEDDERS:
                notes = self._embed(key, [f"{e['name']}: {e.get('note') or ''}" for e in self.entries], False)
                filed = self._embed(key, [self.filed[k][0] for k in self.filed_keys], False)
                self._emb[key] = (notes, filed)
            if getattr(self, '_members', None) is None:
                self.nomic(claim, leave_out)  # the motifs' members, by filed claim
        k = mi.key(claim)
        skip = self.filed_keys.index(k) if leave_out and k in self.filed else -1
        out = {}
        for key, (notes, filed) in self._emb.items():
            q = self._embed(key, [claim], True)[0]
            sims = filed @ q
            out[f'{key} note'] = notes @ q
            out[f'{key} near'] = np.array([max((sims[i] for i in rows if i != skip), default=-1.0) for rows in self._members])
        return out

    # ---- costly signals, for a shortlist ----

    def nearest_claims(self, claim: str, n: int, leave_out: bool, count: int = 3) -> list[str]:
        k = mi.key(claim)
        own = [x['claim'] for x in self.entries[n]['claims'] if not (leave_out and mi.key(x['claim']) == k)]
        if not own:
            return []
        sims = self.vec(own) @ self.vec([claim])[0]
        return [own[i] for i in np.argsort(-sims)[:count]]

    def _document(self, n: int, examples: list[str]) -> str:
        e = self.entries[n]
        return (f"{e.get('note') or e['name']} (nicknamed “{e['name']}”)"
                + (' Claims filed under it: ' + '; '.join(c[:160] for c in examples) if examples else ''))

    def rerank(self, claim: str, ns: list[int], leave_out: bool = False) -> np.ndarray:
        todo, keys = [], []
        for n in ns:
            doc = self._document(n, self.nearest_claims(claim, n, leave_out, 2))
            h = pair_hash(claim, doc) if self.rerank_tag == 'base' else pair_hash(self.rerank_tag, claim, doc)
            keys.append(h)
            if h not in self.reranks:
                todo.append((h, doc))
        if todo:
            for (h, _), p in zip(todo, self._rerank_batch(claim, [d for _, d in todo])):
                self.reranks[h] = round(p, 5)
        return np.array([self.reranks[h] for h in keys])

    def _rerank_batch(self, claim: str, docs: list[str]) -> list[float]:
        import torch
        if self._reranker is None:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            free = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
            device = os.environ.get('MOTIF_RERANK_DEVICE') or ('cuda' if free > 3e9 else 'cpu')  # Gemma may hold the GPU
            tok = AutoTokenizer.from_pretrained(RERANKER, padding_side='left')
            from app.analysis import reranker_teach  # the layers taught the person's taste, if taught yet
            model = AutoModelForCausalLM.from_pretrained(RERANKER, dtype=torch.float16 if device == 'cuda' else torch.float32)
            model = reranker_teach.load_into(model).to(device).eval()
            self._reranker = (tok, model, device, tok.convert_tokens_to_ids('yes'), tok.convert_tokens_to_ids('no'))
            logger.info("Reranker (%s) on %s", self.rerank_tag, device)
        tok, model, device, yes, no = self._reranker
        out = []
        for i in range(0, len(docs), 8):
            texts = [rerank_text(claim, d) for d in docs[i:i + 8]]
            batch = tok(texts, padding=True, truncation=True, max_length=1024, return_tensors='pt').to(device)
            with torch.no_grad():
                logits = model(**batch).logits[:, -1, :]
            pair = torch.stack([logits[:, no], logits[:, yes]], 1).float().log_softmax(1)
            out += pair[:, 1].exp().tolist()
        return out

    def judge(self, claim: str, ns: list[int], leave_out: bool = False) -> np.ndarray:
        """The judge's P(yes) for the claim in each motif (JUDGE_DECIDER, or Gemma's yes or no), cached"""
        return self.judge_many([(claim, ns)], leave_out)[0]

    def judge_ask(self, claim: str, n: int, leave_out: bool = False) -> tuple[str, str]:
        """(cache key, text) of the judge's question for the claim in motif n"""
        e = self.entries[n]
        ex = self.nearest_claims(claim, n, leave_out, 3)
        if JUDGE_DECIDER:
            need = self.element_of(e)
            text = (f"Motif: {e['name']}\nWhat it covers: {e.get('note') or '(no note yet)'}\n"
                    + (f'{ELEMENT_LINE} {need}\n' if need else '') + "Claims filed under it:\n"
                    + '\n'.join(f'- {c[:300]}' for c in ex) + f'\n\nNew claim: {claim}')
            return pair_hash(JUDGE_DECIDER, text), text
        text = JUDGE_PROMPT.format(name=e['name'], note=e.get('note') or '(no note yet)',
                                   examples='\n'.join(f'- {c}' for c in ex) or '(none yet)', claim=claim)
        return pair_hash(text), text

    def judge_many(self, items: list[tuple[str, list[int]]], leave_out: bool = False,
                   budget: float | None = None) -> list[np.ndarray]:
        """judge() for many claims at once: the pairs not asked yet llm.PARALLEL at once, in one go, so the judge is
        loaded once (Nimble and Gemma 26B don't fit the card together); with `budget`, those not begun by then wait
        (0.5 meanwhile: see judge_missing)"""
        from app.analysis import llm
        start = time.time()
        self.draft_elements(sorted({n for _, ns in items for n in ns}), budget)  # Gemma first, then the judge: not both
        if budget is not None:
            budget = max(0.0, budget - (time.time() - start))
        asks = [[self.judge_ask(claim, n, leave_out) for n in ns] for claim, ns in items]
        todo = list({h: t for row in asks for h, t in row if h not in self.judged}.items())
        for (h, _), p in zip(todo, llm.parallel(lambda x: _judge_one(x[1]), todo, budget=budget)):
            if p is not None:
                self.judged[h] = p
        return [np.array([self.judged.get(h, 0.5) for h, _ in row]) for row in asks]

    @staticmethod
    def element_source(e: dict) -> str:
        return pair_hash(e['name'], mi.genre_of(e) or '', e.get('note') or '')

    def element_of(self, e: dict) -> str | None:
        """The motif's must-have element, if drafted from what it says now"""
        if not (JUDGE_DECIDER and JUDGE_ELEMENTS):
            return None
        got = self.elements.get(e['id']) or {}
        return got.get('element') if got.get('from') == self.element_source(e) else None

    def draft_elements(self, ns: list[int], budget: float | None = None) -> int:
        """Draft the element of each of these motifs that has none, or one from an old name, genre or note (Gemma
        26B, llm.PARALLEL at once); how many were drafted"""
        if not (JUDGE_DECIDER and JUDGE_ELEMENTS):
            return 0
        from app.analysis import llm
        todo = [self.entries[n] for n in ns if self.element_of(self.entries[n]) is None]

        def one(e):
            a = llm.complete_json(ELEMENT_PROMPT.format(name=e['name'], genre=mi.genre_of(e) or 'none yet',
                                                        note=e.get('note') or '(no note yet)'),
                                  ELEMENT_SCHEMA, max_tokens=200, model=JUDGE_MODEL)
            return ' '.join(a['element'].split()) if a and a.get('element') else None
        made = 0
        for e, got in zip(todo, llm.parallel(one, todo, budget=budget)):
            if got:
                self.elements[e['id']] = {'element': got, 'from': self.element_source(e)}
                made += 1
        if made:
            write_json(ELEMENTS, self.elements)
            logger.info("Judge: drafted the must-have element of %d motifs", made)
        return made

    def judge_missing(self, items: list[tuple[str, list[int]]], leave_out: bool = False) -> int:
        """How many of these pairs the judge hasn't answered yet"""
        return sum(1 for claim, ns in items for n in ns if self.judge_ask(claim, n, leave_out)[0] not in self.judged)

    def save(self):
        """The costly answers, kept for the next run"""
        write_json(SHAPES, self.shapes)
        write_json(LAYERED, self.layered)
        write_json(RERANKS, self.reranks)
        write_json(JUDGED, self.judged)


def as_dict(arrays: dict, n: int) -> dict:
    return {k: float(v[n]) for k, v in arrays.items()}


def describe() -> str:
    return json.dumps({'cheap': CHEAP, 'costly': ['rerank', 'judge'], 'reranker': RERANKER, 'judge': judge_tag(),
                       'second embedder': NOMIC,
                       'news out': f'{NEWS_DIRECTIONS} directions of the latest {NEWS_HEADLINES} headlines'})
