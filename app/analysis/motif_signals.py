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
from collections import Counter

import numpy as np

from app.analysis import motif_index as mi
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'motifs')
SHAPES = os.path.join(FOLDER, 'claim_shapes.json')  # claim key -> its bare shape, by the filing model
RERANKS = os.path.join(FOLDER, 'rerank_cache.json')  # pair hash -> the reranker's P(yes)
JUDGED = os.path.join(FOLDER, 'pair_judge_cache.json')  # pair hash -> the filing model's P(yes)
NOMIC = 'nomic-embed-text'
RERANKER = 'Qwen/Qwen3-Reranker-0.6B'
JUDGE_MODEL = 'gemma4:26b'
NEIGHBOURS = 15
STOP = {'a', 'an', 'the', 'and', 'or', 'but', 'if', 'of', 'to', 'in', 'on', 'at', 'by', 'for', 'with', 'from', 'as',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'it', 'its', 'this', 'that', 'these', 'those', 'he',
        'she', 'they', 'them', 'his', 'her', 'their', 'we', 'our', 'you', 'your', 'i', 'me', 'my', 'not', 'no', 'so',
        'than', 'then', 'there', 'here', 'what', 'which', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how',
        'all', 'any', 'some', 'more', 'most', 'other', 'such', 'only', 'own', 'same', 'too', 'very', 'can', 'will',
        'just', 'should', 'now', 'says', 'said', 'say', 'about', 'into', 'over', 'after', 'before', 'also', 'has',
        'have', 'had', 'do', 'does', 'did', 'would', 'could', 'may', 'might', 'must', 'one', 'two', 'new', 'people'}
WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
CHEAP = ['keywords', 'note', 'shape', 'votes', 'nomic desc', 'nomic near']

SHAPE_PROMPT = """A claim people are telling or arguing over:
{claim}

Restate it as the bare shape of the story it tells, in one plain sentence: what its tellers say is true, with kinds of \
people, places and things in place of particular ones ("a party leader", "immigrants", "a foreign power"), and no \
names or dates. Keep what makes it this story and not another."""
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
        self.reranks = read_json(RERANKS, {})
        self.judged = read_json(JUDGED, {})
        self._reranker = None

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

    def cheap(self, claim: str, leave_out: bool = False, ask: bool = True) -> dict[str, np.ndarray]:
        """Every cheap signal against every motif"""
        desc, near = self.nomic(claim, leave_out)
        return {'keywords': self.keywords(claim, leave_out), 'note': self.note(claim), 'shape': self.shape(claim, ask),
                'votes': self.votes(claim, leave_out), 'nomic desc': desc, 'nomic near': near}

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
            h = pair_hash(claim, doc)
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
            model = AutoModelForCausalLM.from_pretrained(RERANKER, torch_dtype=torch.float16 if device == 'cuda' else torch.float32).to(device).eval()
            self._reranker = (tok, model, device, tok.convert_tokens_to_ids('yes'), tok.convert_tokens_to_ids('no'))
            logger.info("Reranker on %s", device)
        tok, model, device, yes, no = self._reranker
        pre = ('<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct '
               'provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n')
        post = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
        out = []
        for i in range(0, len(docs), 8):
            texts = [f'{pre}<Instruct>: {RERANK_TASK}\n<Query>: {claim}\n<Document>: {d}{post}' for d in docs[i:i + 8]]
            batch = tok(texts, padding=True, truncation=True, max_length=1024, return_tensors='pt').to(device)
            with torch.no_grad():
                logits = model(**batch).logits[:, -1, :]
            pair = torch.stack([logits[:, no], logits[:, yes]], 1).float().log_softmax(1)
            out += pair[:, 1].exp().tolist()
        return out

    def judge(self, claim: str, ns: list[int], leave_out: bool = False) -> np.ndarray:
        import requests as rq
        from app.analysis.llm import OLLAMA_URL
        out = []
        for n in ns:
            e = self.entries[n]
            ex = self.nearest_claims(claim, n, leave_out, 3)
            prompt = JUDGE_PROMPT.format(name=e['name'], note=e.get('note') or '(no note yet)',
                                         examples='\n'.join(f'- {c}' for c in ex) or '(none yet)', claim=claim)
            h = pair_hash(prompt)
            if h not in self.judged:
                r = rq.post(f'{OLLAMA_URL}/api/chat', timeout=300, json={
                    'model': JUDGE_MODEL, 'messages': [{'role': 'user', 'content': prompt}], 'think': False,
                    'stream': False, 'logprobs': True, 'top_logprobs': 10, 'options': {'temperature': 0, 'num_predict': 1}})
                r.raise_for_status()
                y = no = -math.inf
                for t in ((r.json().get('logprobs') or [{}])[0].get('top_logprobs') or []):
                    w = t['token'].strip().lower()
                    if w.startswith('yes'):
                        y = max(y, t['logprob'])
                    elif w.startswith('no'):
                        no = max(no, t['logprob'])
                self.judged[h] = 0.5 if y == no == -math.inf else (1.0 if no == -math.inf else 0.0 if y == -math.inf
                                                                   else round(1 / (1 + math.exp(no - y)), 5))
            out.append(self.judged[h])
        return np.array(out)

    def save(self):
        """The costly answers, kept for the next run"""
        write_json(SHAPES, self.shapes)
        write_json(RERANKS, self.reranks)
        write_json(JUDGED, self.judged)


def as_dict(arrays: dict, n: int) -> dict:
    return {k: float(v[n]) for k, v in arrays.items()}


def describe() -> str:
    return json.dumps({'cheap': CHEAP, 'costly': ['rerank', 'judge'], 'reranker': RERANKER, 'second embedder': NOMIC})
