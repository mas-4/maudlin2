// Keyword search over the motif index (motifs.html's search box, Oct 28): BM25 over each motif's name, tellers'
// phrases, note and claims, from motif-search.json. The scoring is app/site/motif_search.py's, line for line, and
// tests/test_motif_search.py checks the two agree under node: change one, change both.
(function (root) {
    'use strict';
    const WEIGHTS = {n: 3.0, p: 2.0, t: 1.5, c: 1.0};
    const K1 = 1.2, B = 0.75, NAME_BOOST = 2.0, PHRASE_BOOST = 1.5, NAME_SHARE = 0.6, TEXT_BOOST = 1.15;
    const STOP = new Set(`a an the of to in on for and or but is are was were be been being it its this that these those by with as at
from into about than then so such not no do does did has have had he she they them his her their we you i will would
can could should may might must said says say who what which when where why how all any some more most other own same
very just also there here out up over only after before because while if theyre theyve theyll its im youre were
dont doesnt didnt isnt arent wasnt werent wont cant us our your my me him`.split(/\s+/));
    const IRREGULAR = {stolen: 'steal', stole: 'steal', children: 'child', men: 'man', women: 'woman',
                       bought: 'buy', lied: 'lie', lying: 'lie', dying: 'die', killed: 'kill'};
    const DOUBLES = /([bcdfgkmnprt])\1$/;

    function stem(w) {
        if (Object.prototype.hasOwnProperty.call(IRREGULAR, w)) return IRREGULAR[w];
        if (w.length <= 3) return w;
        if (w.endsWith('ies') && w.length > 4) w = w.slice(0, -3) + 'y';
        else if (w.endsWith('sses')) w = w.slice(0, -2);
        else if (w.endsWith('s') && !w.endsWith('ss') && !w.endsWith('us') && !w.endsWith('is')) w = w.slice(0, -1);
        for (const suffix of ['ing', 'ed']) {
            const rest = w.slice(0, -suffix.length);
            if (w.endsWith(suffix) && rest.length >= 3 && /[aeiouy]/.test(rest)) {
                w = rest.replace(DOUBLES, '$1');
                break;
            }
        }
        if (w.endsWith('e') && w.length > 3) w = w.slice(0, -1);
        return w;
    }

    function fold(text) {
        return String(text || '').toLowerCase().normalize('NFKD').replace(/\p{Mn}/gu, '').replace(/’/g, "'").replace(/'/g, '');
    }

    function tokens(text) {
        return fold(text).split(/[^a-z0-9]+/).filter((w) => w.length > 1 && !STOP.has(w)).map(stem);
    }

    function within(q, words) {
        for (let j = 0; j + q.length <= words.length; j++) {
            let all = true;
            for (let k = 0; k < q.length; k++) if (words[j + k] !== q[k]) { all = false; break; }
            if (all) return true;
        }
        return false;
    }

    function Search(docs) {
        this.docs = docs;
        this.fields = [];
        this.tf = [];
        this.len = [];
        for (const d of docs) {
            const f = {n: tokens(d.n), p: d.p.map(tokens), t: tokens(d.t), c: d.c.map(tokens)};
            const tf = new Map();
            for (const [key, words] of [['n', f.n], ['p', f.p.flat()], ['t', f.t], ['c', f.c.flat()]]) {
                for (const w of words) tf.set(w, (tf.get(w) || 0) + WEIGHTS[key]);
            }
            let total = 0;
            for (const v of tf.values()) total += v;
            this.fields.push(f);
            this.tf.push(tf);
            this.len.push(total);
        }
        this.avg = this.len.reduce((a, b) => a + b, 0) / Math.max(this.len.length, 1);
        this.df = new Map();
        for (const tf of this.tf) for (const w of tf.keys()) this.df.set(w, (this.df.get(w) || 0) + 1);
    }

    Search.prototype.scores = function (query) {
        const q = tokens(query);
        const terms = [...new Set(q)];
        const n = this.docs.length;
        return this.tf.map((tf, i) => {
            let s = 0;
            for (const w of terms) {
                const f = tf.get(w);
                if (!f) continue;
                const df = this.df.get(w);
                const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
                s += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * this.len[i] / this.avg));
            }
            if (s && q.length) {
                const name = this.fields[i].n;
                if (within(q, name)) s *= NAME_BOOST;
                else if (this.fields[i].p.some((p) => within(q, p))) s *= PHRASE_BOOST;
                else s *= 1 + NAME_SHARE * terms.filter((w) => name.includes(w)).length / terms.length;
                if (q.length > 1 && (within(q, this.fields[i].t) || this.fields[i].c.some((c) => within(q, c)))) s *= TEXT_BOOST;
            }
            return s;
        });
    };

    // The best motifs, best first (ties by most claims, then name): [{doc, score}]
    Search.prototype.top = function (query, n) {
        const s = this.scores(query);
        const r = (x) => Math.round(x * 1e9) / 1e9;
        return s.map((score, i) => ({i, score})).filter((x) => x.score > 0)
            .sort((a, b) => (r(b.score) - r(a.score)) || (this.docs[b.i].k - this.docs[a.i].k)
                || (this.docs[a.i].n < this.docs[b.i].n ? -1 : this.docs[a.i].n > this.docs[b.i].n ? 1 : 0))
            .slice(0, n || 8).map((x) => ({doc: this.docs[x.i], score: x.score}));
    };

    const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[ch]));

    // A line from the motif to show under its name: its note or the claim with most of the query's words, cut near the
    // first of them, as html with those words marked
    function snippet(doc, query, size) {
        size = size || 170;
        const want = new Set(tokens(query));
        const words = (text) => (fold(text).match(/[a-z0-9]+/g) || []).filter((w) => w.length > 1 && !STOP.has(w)).map(stem);
        let best = doc.t, most = -1;
        for (const text of [doc.t, ...doc.c]) {
            const hits = new Set(words(text).filter((w) => want.has(w))).size;
            if (hits > most) { best = text; most = hits; }
        }
        if (!best) return '';
        const marks = [];
        for (const m of best.matchAll(/[\p{L}\p{N}'’]+/gu)) {
            if (words(m[0]).some((w) => want.has(w))) marks.push([m.index, m.index + m[0].length]);
        }
        let start = 0;
        if (marks.length && marks[0][0] > size / 2) start = best.lastIndexOf(' ', marks[0][0] - size / 3) + 1;
        let end = Math.min(best.length, start + size);
        if (end < best.length) end = Math.max(best.lastIndexOf(' ', end), start + 1);
        let out = '', at = start;
        for (const [a, b] of marks) {
            if (a < start || b > end) continue;
            out += esc(best.slice(at, a)) + '<mark>' + esc(best.slice(a, b)) + '</mark>';
            at = b;
        }
        out += esc(best.slice(at, end));
        return (start > 0 ? '…' : '') + out + (end < best.length ? '…' : '');
    }

    const api = {Search, tokens, stem, snippet};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.MotifSearch = api;
})(typeof window !== 'undefined' ? window : globalThis);
