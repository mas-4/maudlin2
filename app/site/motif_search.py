"""Keyword search over the motif index, for the search box on motifs.html (Oct 28).

At build time `build()` writes a compact index of the motifs that have pages: each one's id, page, name, genre, note,
tellers' phrases and public claims. The page fetches it the first time a reader uses the box, and
`app/site/static/motif-search.js` ranks the motifs in the browser with BM25 over those fields: no model, no server.
The Oct 27 probe (maudlin-notes, moonshot ml section 5) found a relevant motif in the top five for 19 of 20 visitor
queries this way.

The scoring here is the same as the script's, line for line, so it can be tested in Python (tests/test_motif_search.py
also runs the script under node, when there is one, and checks the two agree). Change one, change both."""
import json
import math
import os
import re
import unicodedata

from app.analysis import motif_index
from app.site.common import motif_href
from app.utils import Config

FILE = 'motif-search.json'
CLAIMS_EACH = 40  # a motif's most recent claims that go in; the biggest have hundreds, and 40 carry its words
CLAIM_CHARS = 280  # a claim cut to this many characters (the longest run to paragraphs)
PHRASES_EACH = 20

# Field weights: a word in the name counts three times one in a claim; the tellers' phrases twice; the note 1.5
WEIGHTS = {'n': 3.0, 'p': 2.0, 't': 1.5, 'c': 1.0}
K1, B = 1.2, 0.75
NAME_BOOST, PHRASE_BOOST = 2.0, 1.5  # the query's words in a row, in the name or in one of the phrases
NAME_SHARE = 0.6  # and short of that, up to 1.6 times as the share of the query's words the name has
TEXT_BOOST = 1.15  # and a query of two words or more in a row in the note or a claim ("deep state", not "deep" alone)

STOP_WORDS = """a an the of to in on for and or but is are was were be been being it its this that these those by with as at
from into about than then so such not no do does did has have had he she they them his her their we you i will would
can could should may might must said says say who what which when where why how all any some more most other own same
very just also there here out up over only after before because while if theyre theyve theyll its im youre were
dont doesnt didnt isnt arent wasnt werent wont cant us our your my me him"""  # the same list in motif-search.js
STOP = set(STOP_WORDS.split())
# Irregular forms the suffixes miss, as their stems: "stolen election" should find what "steal" does
IRREGULAR = {'stolen': 'steal', 'stole': 'steal', 'children': 'child', 'men': 'man', 'women': 'woman',
             'bought': 'buy', 'lied': 'lie', 'lying': 'lie', 'dying': 'die', 'killed': 'kill'}
DOUBLES = re.compile(r'([bcdfgkmnprt])\1$')  # "rigg" -> "rig", "stopp" -> "stop"; not ll, ss, zz


def stem(w: str) -> str:
    """A light suffix stripper (plurals, -ing, -ed, a final e), the same in motif-search.js"""
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) <= 3:
        return w
    if w.endswith('ies') and len(w) > 4:
        w = w[:-3] + 'y'
    elif w.endswith('sses'):
        w = w[:-2]
    elif w.endswith('s') and not w.endswith(('ss', 'us', 'is')):
        w = w[:-1]
    for suffix in ('ing', 'ed'):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3 and re.search(r'[aeiouy]', w[:-len(suffix)]):
            w = DOUBLES.sub(r'\1', w[:-len(suffix)])
            break
    if w.endswith('e') and len(w) > 3:
        w = w[:-1]
    return w


def tokens(text: str) -> list[str]:
    """Stemmed words, accents and apostrophes gone, stop words out: the same in motif-search.js"""
    text = unicodedata.normalize('NFKD', str(text or '').lower())
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn').replace('’', "'").replace("'", '')
    return [stem(w) for w in re.split(r'[^a-z0-9]+', text) if len(w) > 1 and w not in STOP]


def doc(e: dict, index_entry: dict) -> dict:
    """One motif as the search reads it"""
    phrases = list(dict.fromkeys([p for p, _ in motif_index.carrying(index_entry)] + index_entry.get('phrases', [])))
    phrases = [p for p in phrases if p.lower() != e['name'].lower()][:PHRASES_EACH]
    claims = list(dict.fromkeys(' '.join(c['claim'].split()) for c in e['claims']))[:CLAIMS_EACH]
    claims = [c if len(c) <= CLAIM_CHARS else c[:CLAIM_CHARS - 1].rsplit(' ', 1)[0] + '…' for c in claims]
    href = motif_href(e['id'])  # the index page's card, for a motif without a page of its own this build
    return {'i': e['id'], 'u': href if href != 'motifs.html' else f"motifs.html#{e['id']}", 'n': e['name'],
            'g': e.get('genre') or '', 't': e.get('note') or '', 'p': phrases, 'c': claims, 'k': e['count']}


def build(entries: list[dict], index: dict) -> dict:
    """The search index for the catalog's motifs (page_motifs.catalog, which has already screened their claims)"""
    return {'v': 1, 'docs': [doc(e, index['entries'].get(e['id'], {})) for e in entries]}


def write(entries: list[dict], index: dict) -> int:
    """Writes the index beside the page; its size in bytes"""
    data = json.dumps(build(entries, index), separators=(',', ':'), ensure_ascii=False)
    with open(os.path.join(Config.build, FILE), 'w', encoding='utf-8') as f:
        f.write(data)
    return len(data.encode())


class Search:
    """BM25 over the weighted fields, as motif-search.js ranks them"""

    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.fields = []
        self.tf, self.len = [], []
        for d in docs:
            f = {'n': tokens(d['n']), 'p': [tokens(p) for p in d['p']], 't': tokens(d['t']),
                 'c': [tokens(c) for c in d['c']]}
            tf = {}
            for key, words in (('n', f['n']), ('p', [w for p in f['p'] for w in p]), ('t', f['t']), ('c', [w for c in f['c'] for w in c])):
                for w in words:
                    tf[w] = tf.get(w, 0) + WEIGHTS[key]
            self.fields.append(f)
            self.tf.append(tf)
            self.len.append(sum(tf.values()))
        self.avg = sum(self.len) / max(len(self.len), 1)
        self.df = {}
        for tf in self.tf:
            for w in tf:
                self.df[w] = self.df.get(w, 0) + 1

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        terms = list(dict.fromkeys(q))
        n = len(self.docs)
        out = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for w in terms:
                f = tf.get(w)
                if not f:
                    continue
                idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                s += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
            if s and q:
                name = self.fields[i]['n']
                if within(q, name):
                    s *= NAME_BOOST
                elif any(within(q, p) for p in self.fields[i]['p']):
                    s *= PHRASE_BOOST
                else:
                    s *= 1 + NAME_SHARE * sum(w in name for w in terms) / len(terms)
                if len(q) > 1 and (within(q, self.fields[i]['t']) or any(within(q, c) for c in self.fields[i]['c'])):
                    s *= TEXT_BOOST
            out.append(s)
        return out

    def top(self, query: str, n: int = 8) -> list[str]:
        """The best motifs' names, best first (ties by most claims, then name)"""
        s = self.scores(query)
        order = sorted((i for i in range(len(s)) if s[i] > 0),
                       key=lambda i: (-round(s[i], 9), -self.docs[i]['k'], self.docs[i]['n']))
        return [self.docs[i]['n'] for i in order[:n]]


def within(q: list[str], words: list[str]) -> bool:
    """The query's words, in order and in a row, among these"""
    return any(words[j:j + len(q)] == q for j in range(len(words) - len(q) + 1))
