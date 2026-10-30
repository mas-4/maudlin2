// Motif space (app/analysis/motif_space.py): every motif's centre and its claims laid out by meaning, drawn on a canvas
// with its own pan, zoom and pinch. The data rides in the page (#ms-data); the public page (motif-space.html) and the
// person's own copy (scripts/motif_map.py) share this script and its markup's ids.
(() => {
    const root = document.getElementById('motif-space');
    const D = JSON.parse(document.getElementById('ms-data').textContent);
    if (!root || !D.motifs.length) return;
    // The site's genre colors (app/site/boards.py GENRE_INK): five big genres, the rest white and known by their emoji
    const GENRE_INK = {Archetypes: '#e87ba4', Plots: '#a0522d', Beliefs: '#7a8a00', Theories: '#8a5cff', Arguments: '#eda100'};
    const GENRE_EMOJI = {Archetypes: '🎭', Plots: '📜', Beliefs: '🪨', Theories: '🕵️', Arguments: '🗣️', Values: '⚖️',
        Exhortations: '📣', Perennials: '🌻'};
    const SPACE_LABEL = {'qwen3 8b': '🧠 By meaning', 'mxbai': '🧪 By the filing’s reading', 'tfidf': '🔤 By shared words'};
    const SPACE_ABOUT = {'qwen3 8b': 'an embedding model (Qwen3-Embedding 8B) reading what each claim says',
        'mxbai': 'the embedding model the filing itself uses (mxbai)', 'tfidf': 'the words each claim shares with the others (TF-IDF)'};
    const INK = '#1f1f2e', PINK = '#ff4fa3', YELLOW = '#ffc400', TEAL = '#00c2a8', PURPLE = '#8a5cff';
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const M = D.motifs.map((m, i) => ({...m, i, claims: []}));
    const C = D.claims;
    C.forEach((c, ci) => c.m.forEach(([mi, ok, d]) => M[mi] && M[mi].claims.push({ci, ok: !!ok, d})));
    const related = new Map(M.map((m) => [m.i, new Set()]));
    (D.related || []).forEach(([a, b]) => { related.get(a).add(b); related.get(b).add(a); });
    const restedOn = new Map(M.map((m) => [m.i, new Set()]));
    M.forEach((m) => (m.rests || []).forEach((p) => restedOn.get(p) && restedOn.get(p).add(m.i)));

    const state = {space: D.spaces[0], sel: null, hover: null, hoverClaim: null, genre: null, group: '', q: '',
        showClaims: false, showLinks: false, focusClaim: null};
    try { const s = localStorage.getItem('motifspace.space'); if (D.spaces.includes(s)) state.space = s; } catch (e) { /* no storage */ }

    // ---- controls
    const spaces = $('ms-spaces');
    D.spaces.forEach((s) => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'ms-pill'; b.textContent = SPACE_LABEL[s] || s; b.dataset.s = s;
        b.addEventListener('click', () => {
            state.space = s;
            try { localStorage.setItem('motifspace.space', s); } catch (e) { /* no storage */ }
            syncSpaces(); renderPanel(); draw();
        });
        spaces.appendChild(b);
    });
    function syncSpaces() {
        spaces.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.s === state.space));
        const about = $('ms-about'); if (about) about.textContent = `Placed by ${SPACE_ABOUT[state.space] || state.space}.`;
    }
    syncSpaces();

    const genres = $('ms-genres'), count = {};
    M.forEach((m) => { count[m.genre] = (count[m.genre] || 0) + 1; });
    (D.genres || []).filter((g) => count[g]).forEach((g) => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'ms-chip'; b.dataset.g = g; b.setAttribute('aria-pressed', 'false');
        b.innerHTML = `${GENRE_INK[g] ? `<span class="ms-swatch" style="background:${GENRE_INK[g]}"></span>` : ''}${GENRE_EMOJI[g] || ''} ${esc(g)} <span class="ms-n">${count[g]}</span>`;
        b.addEventListener('click', () => {
            state.genre = state.genre === g ? null : g;
            genres.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', x.dataset.g === state.genre));
            draw();
        });
        genres.appendChild(b);
    });
    const groupSel = $('ms-group');
    Object.entries(D.groups || {}).sort((a, b) => a[1].localeCompare(b[1])).forEach(([id, name]) => {
        const n = M.filter((m) => (m.groups || []).includes(id)).length;
        if (!n) return;
        const o = document.createElement('option'); o.value = id; o.textContent = `${name} (${n})`; groupSel.appendChild(o);
    });
    groupSel.addEventListener('change', () => { state.group = groupSel.value; draw(); });
    const find = $('ms-find');
    find.addEventListener('input', () => { state.q = find.value.trim().toLowerCase(); draw(); });
    find.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        const hit = M.find((m) => matches(m) && m.xy && m.xy[state.space]);
        if (hit) select(hit.i, true);
    });
    $('ms-show-claims').addEventListener('change', (e) => { state.showClaims = e.target.checked; draw(); });
    $('ms-show-links').addEventListener('change', (e) => { state.showLinks = e.target.checked; draw(); });

    function matches(m) {
        if (state.genre && m.genre !== state.genre) return false;
        if (state.group && !(m.groups || []).includes(state.group)) return false;
        if (state.q && !(m.name.toLowerCase().includes(state.q) || (m.note || '').toLowerCase().includes(state.q)
                         || m.id.toLowerCase() === state.q)) return false;
        return true;
    }
    const filtering = () => !!(state.genre || state.group || state.q);

    // ---- the canvas, panned and zoomed by hand: a view {k, x, y} over the unzoomed layout
    const card = $('ms-card'), canvas = $('ms-canvas'), ctx = canvas.getContext('2d'), tip = $('ms-tip');
    let W = 0, H = 0, T = {k: 1, x: 0, y: 0};
    const PAD = 26;
    function base(p) {  // the layout's 0..1000 square into the card, keeping its aspect
        const s = Math.min(W - 2 * PAD, H - 2 * PAD) / 1000;
        return [(W - 1000 * s) / 2 + p[0] * s, (H - 1000 * s) / 2 + p[1] * s];
    }
    const scr = (p) => { const b = base(p); return [b[0] * T.k + T.x, b[1] * T.k + T.y]; };
    function resize() {
        const r = card.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
        W = r.width; H = r.height; canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); draw();
    }
    new ResizeObserver(resize).observe(card);
    const clampK = (k) => Math.max(0.7, Math.min(60, k));
    function zoomAt(cx, cy, factor) {
        const k = clampK(T.k * factor), f = k / T.k;
        T = {k, x: cx - (cx - T.x) * f, y: cy - (cy - T.y) * f}; draw();
    }
    let anim = null;
    function flyTo(target) {
        cancelAnimationFrame(anim);
        if (reduced) { T = target; draw(); return; }
        const from = {...T}, t0 = performance.now();
        const step = (now) => {
            const t = Math.min(1, (now - t0) / 420), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
            T = {k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e};
            draw();
            if (t < 1) anim = requestAnimationFrame(step);
        };
        anim = requestAnimationFrame(step);
    }
    $('ms-zin').onclick = () => zoomAt(W / 2, H / 2, 1.8);
    $('ms-zout').onclick = () => zoomAt(W / 2, H / 2, 1 / 1.8);
    $('ms-zreset').onclick = () => flyTo({k: 1, x: 0, y: 0});
    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const r = canvas.getBoundingClientRect();
        zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0016)));
    }, {passive: false});
    const pointers = new Map();
    let drag = null;
    canvas.addEventListener('pointerdown', (e) => {
        canvas.setPointerCapture(e.pointerId);
        pointers.set(e.pointerId, [e.clientX, e.clientY]);
        drag = {x: e.clientX, y: e.clientY, moved: 0, pinch: pointers.size > 1 ? pinchOf() : null};
    });
    function pinchOf() {
        const [a, b] = [...pointers.values()];
        return {d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2};
    }
    canvas.addEventListener('pointermove', (e) => {
        const r = canvas.getBoundingClientRect();
        if (pointers.has(e.pointerId) && drag) {
            const last = pointers.get(e.pointerId);
            pointers.set(e.pointerId, [e.clientX, e.clientY]);
            if (pointers.size > 1 && drag.pinch) {
                const now = pinchOf();
                zoomAt(now.cx - r.left, now.cy - r.top, now.d / drag.pinch.d);
                T = {...T, x: T.x + now.cx - drag.pinch.cx, y: T.y + now.cy - drag.pinch.cy};
                drag.pinch = now; drag.moved += 10; draw();
                return;
            }
            const dx = e.clientX - last[0], dy = e.clientY - last[1];
            drag.moved += Math.abs(dx) + Math.abs(dy);
            if (drag.moved > 4) { T = {...T, x: T.x + dx, y: T.y + dy}; tip.hidden = true; draw(); return; }
        }
        hoverAt(e.clientX - r.left, e.clientY - r.top);
    });
    const release = (e) => {
        pointers.delete(e.pointerId);
        if (pointers.size === 0) {
            if (drag && drag.moved <= 4 && e.type === 'pointerup') {
                const r = canvas.getBoundingClientRect();
                clickAt(e.clientX - r.left, e.clientY - r.top);
            }
            drag = null;
        } else if (drag) drag.pinch = pointers.size > 1 ? pinchOf() : null;
    };
    canvas.addEventListener('pointerup', release);
    canvas.addEventListener('pointercancel', release);
    canvas.addEventListener('pointerleave', () => { if (!drag) { tip.hidden = true; state.hover = state.hoverClaim = null; draw(); } });

    // ---- drawing
    const radius = (m) => Math.min(15, 2.6 + Math.sqrt(m.claims.length) * 1.15) * Math.min(1.7, Math.sqrt(T.k));
    function line(a, b, color, width, dash) {
        ctx.beginPath(); ctx.setLineDash(dash || []); ctx.strokeStyle = color; ctx.lineWidth = width;
        ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); ctx.setLineDash([]);
    }
    function dot(p, r, fill, stroke, sw) {
        ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, Math.PI * 2);
        if (fill) { ctx.fillStyle = fill; ctx.fill(); }
        if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = sw || 1; ctx.stroke(); }
    }
    function label(p, text, size, placed) {
        ctx.font = `700 ${size}px 'Comic Neue', 'Comic Sans MS', cursive`;
        const w = ctx.measureText(text).width, x = p[0] + 8, y = p[1] - 6;
        const box = [x - 2, y - size, x + w + 2, y + 4];
        if (placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) return;
        placed.push(box);
        ctx.lineJoin = 'round'; ctx.lineWidth = 4; ctx.strokeStyle = '#fff'; ctx.strokeText(text, x, y);
        ctx.fillStyle = INK; ctx.fillText(text, x, y);
    }
    function draw() {
        if (!W) return;
        const sp = state.space;
        ctx.clearRect(0, 0, W, H);
        const on = M.filter((m) => m.xy && m.xy[sp]);
        const pos = new Map(on.map((m) => [m.i, scr(m.xy[sp])]));
        const f = filtering(), hit = new Set(on.filter(matches).map((m) => m.i));
        $('ms-counts').textContent = f ? `${hit.size} of ${on.length} motifs picked out` : `${on.length} motifs · ${C.length} claims`;
        if (state.showLinks) {
            (D.related || []).forEach(([a, b]) => { if (pos.has(a) && pos.has(b)) line(pos.get(a), pos.get(b), 'rgba(0,194,168,.4)', 1); });
            M.forEach((m) => (m.rests || []).forEach((p) => {
                if (pos.has(m.i) && pos.has(p)) line(pos.get(m.i), pos.get(p), 'rgba(138,92,255,.4)', 1);
            }));
        }
        if (state.showClaims) {
            ctx.fillStyle = 'rgba(31,31,46,.22)';
            C.forEach((c) => { const xy = c.xy[sp]; if (!xy) return; const p = scr(xy); ctx.fillRect(p[0] - 1.2, p[1] - 1.2, 2.4, 2.4); });
        }
        const S = state.sel != null ? M[state.sel] : null, sOn = S && pos.has(S.i);
        if (sOn) {
            const c0 = pos.get(S.i);
            related.get(S.i).forEach((j) => pos.has(j) && line(c0, pos.get(j), TEAL, 2, [6, 4]));
            (S.rests || []).forEach((j) => pos.has(j) && line(c0, pos.get(j), PURPLE, 2.5));
            restedOn.get(S.i).forEach((j) => pos.has(j) && line(c0, pos.get(j), PURPLE, 1.5, [2, 3]));
            S.claims.forEach(({ci}) => { const xy = C[ci].xy[sp]; if (xy) line(scr(xy), c0, 'rgba(31,31,46,.35)', 1); });
        }
        const order = on.slice().sort((a, b) => a.claims.length - b.claims.length);  // small first, big on top
        order.forEach((m) => {
            if (S && m.i === S.i) return;
            const dim = f && !hit.has(m.i);
            ctx.globalAlpha = dim ? 0.15 : 1;
            dot(pos.get(m.i), radius(m), GENRE_INK[m.genre] || '#ffffff', INK, f && !dim ? 2 : 1.1);
            ctx.globalAlpha = 1;
        });
        if (sOn) {
            S.claims.forEach(({ci, ok}) => {
                const xy = C[ci].xy[sp]; if (!xy) return;
                const p = scr(xy), focus = state.focusClaim === ci;
                dot(p, focus ? 6 : 3.6, ok ? INK : '#fff', INK, 1.5);
                if (focus) dot(p, 9, null, PINK, 2.5);
            });
            const p = pos.get(S.i), r = radius(S) + 3;
            dot([p[0] + 3, p[1] + 3], r, INK);
            dot(p, r, YELLOW, INK, 2.5);
        }
        if (state.hoverClaim != null) { const xy = C[state.hoverClaim].xy[sp]; if (xy) dot(scr(xy), 5, PINK, INK, 1.5); }
        const placed = [];
        if (sOn) {
            label(pos.get(S.i), S.name, 15, placed);
            ((S.near || {})[sp] || []).slice(0, 5).forEach(([j]) => pos.has(j) && label(pos.get(j), M[j].name, 12, placed));
        }
        if (state.hover != null && pos.has(state.hover)) label(pos.get(state.hover), M[state.hover].name, 13, placed);
        if (f && hit.size <= 40) hit.forEach((i) => label(pos.get(i), M[i].name, 12, placed));
        if (T.k >= 2.6) {
            order.slice().reverse().forEach((m) => {
                const p = pos.get(m.i);
                if (p[0] < 0 || p[1] < 0 || p[0] > W || p[1] > H || (f && !hit.has(m.i))) return;
                label(p, m.name, 11, placed);
            });
        }
    }

    // ---- pointing
    function nearest(px, py) {
        const sp = state.space; let best = null, bd = Infinity;
        M.forEach((m) => {
            if (!m.xy || !m.xy[sp]) return;
            const p = scr(m.xy[sp]), d = Math.hypot(p[0] - px, p[1] - py) - radius(m);
            if (d < bd) { bd = d; best = m.i; }
        });
        return bd <= 8 ? best : null;
    }
    function nearestClaim(px, py) {
        const sp = state.space; let best = null, bd = Infinity;
        const pool = state.showClaims ? C.map((c, ci) => ci) : (state.sel != null ? M[state.sel].claims.map((c) => c.ci) : []);
        pool.forEach((ci) => {
            const xy = C[ci].xy[sp]; if (!xy) return;
            const p = scr(xy), d = Math.hypot(p[0] - px, p[1] - py);
            if (d < bd) { bd = d; best = ci; }
        });
        return bd <= 7 ? best : null;
    }
    function showTip(px, py, html) {
        tip.innerHTML = html; tip.hidden = false;
        const w = tip.offsetWidth, h = tip.offsetHeight;
        tip.style.left = Math.min(W - w - 8, Math.max(8, px + 14)) + 'px';
        tip.style.top = Math.min(H - h - 8, Math.max(8, py + 14)) + 'px';
    }
    function hoverAt(px, py) {
        const m = nearest(px, py), c = m == null ? nearestClaim(px, py) : null;
        const changed = m !== state.hover || c !== state.hoverClaim;
        state.hover = m; state.hoverClaim = c;
        canvas.classList.toggle('ms-over', m != null || c != null);
        if (m != null) {
            const x = M[m];
            showTip(px, py, `<b>${GENRE_EMOJI[x.genre] || ''} ${esc(x.name)}</b>${esc(x.genre || 'no genre')} · ${x.claims.length} claim${x.claims.length === 1 ? '' : 's'}`);
        } else if (c != null) {
            showTip(px, py, `${esc(C[c].t)}<br><span class="ms-small">in ${esc(C[c].m.map(([mi]) => M[mi].name).join(', '))}</span>`);
        } else tip.hidden = true;
        if (changed) draw();
    }
    function clickAt(px, py) {
        const m = nearest(px, py);
        if (m != null) return select(m, false);
        const c = nearestClaim(px, py);
        if (c != null) {
            if (state.sel == null || !C[c].m.some(([mi]) => mi === state.sel)) select(C[c].m[0][0], false);
            state.focusClaim = c; renderPanel(); draw(); return;
        }
        select(null);
    }
    function select(i, fly) {
        state.sel = i; state.focusClaim = null; renderPanel(); draw();
        if (i != null && fly && M[i].xy && M[i].xy[state.space]) {
            const b = base(M[i].xy[state.space]), k = Math.max(T.k, 3);
            flyTo({k, x: W / 2 - b[0] * k, y: H / 2 - b[1] * k});
        }
        if (i != null && window.matchMedia('(max-width: 960px)').matches) $('ms-panel').scrollIntoView({block: 'nearest'});
    }

    // ---- the panel
    const panel = $('ms-panel');
    const rated = M.filter((m) => m.claims.length >= 3 && m.spread != null).sort((a, b) => a.spread - b.spread);
    const pct = (m) => Math.round(100 * rated.filter((x) => x.spread < m.spread).length / Math.max(1, rated.length));
    const row = (m, right) => `<li><button type="button" data-m="${m.i}"><span class="ms-name">${GENRE_EMOJI[m.genre] || '·'} ${esc(m.name)}</span><span class="ms-num">${right}</span></button></li>`;
    function renderPanel() {
        const sp = state.space;
        if (state.sel == null) {
            panel.innerHTML = `
                <div class="ms-stickers">
                    <div class="ms-sticker"><span>🧩 motifs</span><strong>${M.length.toLocaleString()}</strong></div>
                    <div class="ms-sticker"><span>💬 claims</span><strong>${C.length.toLocaleString()}</strong></div>
                </div>
                <p>Poke a dot to open its motif: its claims are drawn around it, tied to its centre, and its nearest neighbours are named.</p>
                <h3>🎯 Tightest motifs</h3>
                <p class="ms-small">Motifs of 3 or more claims whose claims say the most nearly the same thing.</p>
                <ol class="ms-rows">${rated.slice(-8).reverse().map((m) => row(m, m.spread.toFixed(2))).join('')}</ol>
                <h3>🌀 Loosest motifs</h3>
                <p class="ms-small">Motifs whose claims range most widely: a broad shape told about many things${D.public ? '' : ', or one holding two tellings or misfiled claims'}.</p>
                <ol class="ms-rows">${rated.slice(0, 8).map((m) => row(m, m.spread.toFixed(2))).join('')}</ol>`;
        } else {
            const m = M[state.sel];
            const claims = m.claims.slice().sort((a, b) => (a.d ?? 2) - (b.d ?? 2));
            const ds = claims.map((c) => c.d).filter((d) => d != null);
            const lo = Math.min(...ds, 0.3), hi = Math.max(...ds, 0.9);
            const near = (m.near || {})[sp] || [];
            const tags = (j) => (related.get(m.i).has(j) ? '<span class="ms-flag">related</span>' : '')
                + ((m.rests || []).includes(j) ? '<span class="ms-flag">rests on</span>' : '')
                + (restedOn.get(m.i).has(j) ? '<span class="ms-flag">rests on this</span>' : '');
            const groups = (m.groups || []).map((g) => `<span class="ms-tag">🗂️ ${esc((D.groups || {})[g] || g)}</span>`).join('');
            const tight = m.claims.length >= 3 && m.spread != null
                ? `<p class="ms-small">Its claims sit ${m.spread.toFixed(2)} alike to their centre on average: tighter than ${pct(m)}% of motifs with 3 or more claims.</p>` : '';
            const where = m.xy && m.xy[sp] ? '' : '<p class="ms-small">Not placed in this view.</p>';
            panel.innerHTML = `
                <button type="button" class="ms-back" id="ms-back">← all motifs</button>
                <h2>${esc(m.name)}</h2>
                <div class="ms-meta"><span class="ms-tag ms-tilt">${GENRE_EMOJI[m.genre] || '❔'} ${esc(m.genre || 'no genre')}</span>
                    ${D.public ? '' : `<span class="ms-tag">${esc(m.id)}</span>${m.done ? '' : '<span class="ms-tag">✏️ not marked done</span>'}`}${groups}</div>
                ${m.note ? `<p>${esc(m.note)}</p>` : ''}
                ${m.href ? `<p><a class="ms-open" href="${esc(m.href)}">🧩 open its page →</a></p>` : ''}
                ${tight}${where}
                <h3>💬 Its claims, farthest from the centre first</h3>
                <ul class="ms-rows">${claims.map((c) => {
                    const w = c.d == null ? 0 : Math.round(100 * (c.d - lo) / Math.max(0.01, hi - lo));
                    const others = C[c.ci].m.filter(([mi]) => mi !== m.i).map(([mi]) => M[mi].name);
                    return `<li><div class="ms-claim" data-c="${c.ci}"><span class="ms-txt">${esc(C[c.ci].t)}${c.ok || D.public ? '' : '<span class="ms-flag">unchecked</span>'}${others.length ? `<br><span class="ms-small">also in ${esc(others.join(', '))}</span>` : ''}</span><span class="ms-num">${c.d == null ? '—' : c.d.toFixed(2)}</span><span class="ms-bar"><i style="width:${Math.max(3, w)}%"></i></span></div></li>`;
                }).join('')}</ul>
                <h3>🧲 Nearest motifs</h3>
                <p class="ms-small">${esc(SPACE_LABEL[sp] || sp)}: likeness of their centres, from 0 (nothing alike) to 1 (the same).</p>
                <ol class="ms-rows">${near.map(([j, s]) => `<li><button type="button" data-m="${j}"><span class="ms-name">${GENRE_EMOJI[M[j].genre] || '·'} ${esc(M[j].name)}${tags(j)}</span><span class="ms-num">${s.toFixed(2)}</span></button></li>`).join('')}</ol>`;
            $('ms-back').onclick = () => select(null);
            panel.querySelectorAll('.ms-claim').forEach((el) => {
                el.addEventListener('pointerenter', () => { state.focusClaim = +el.dataset.c; draw(); });
                el.addEventListener('pointerleave', () => { state.focusClaim = null; draw(); });
            });
        }
        panel.querySelectorAll('button[data-m]').forEach((b) => b.addEventListener('click', () => select(+b.dataset.m, true)));
    }

    renderPanel();
    resize();
    const start = M.find((m) => m.id === location.hash.slice(1).toUpperCase());
    if (start) setTimeout(() => select(start.i, true), 60);
})();
