// The headline galaxy (galaxy.html, app/site/page_over_time.py): every headline we've read on a canvas that fills the
// page (Nov 5, the person: "make it an entire page you go to"). Its points come from galaxy/points.bin, each headline's
// words from galaxy/t-N.json when someone points at it. Day i of D.days is a headline's day.
(() => {
    const D = JSON.parse(document.getElementById('ot-data').textContent);
    const DAYS = D.days || [];
    const N = DAYS.length;
    const INK = '#1f1f2e';
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
    const dayName = (d) => { const [, m, dd] = d.split('-'); return `${MONTHS[+m - 1]} ${+dd}`; };
    const short = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s);

    const tip = $('ot-tip');
    function showTip(html, x, y) {
        tip.innerHTML = html;
        tip.hidden = false;
        const r = tip.getBoundingClientRect();
        let left = x + 14, top = y + 14;
        if (left + r.width > innerWidth - 8) left = Math.max(8, x - r.width - 14);
        if (top + r.height > innerHeight - 8) top = Math.max(8, y - r.height - 14);
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
    }
    const hideTip = () => { tip.hidden = true; };

    // Back where they came from (keeping their place on that page), or to the charts when they arrived here directly
    $('gx-back').addEventListener('click', (ev) => {
        let same = false;
        try { same = document.referrer && new URL(document.referrer).origin === location.origin; } catch (e) { same = false; }
        if (same && history.length > 1) { ev.preventDefault(); history.back(); }
    });
    // Escape closes an open headline card first, then leaves
    addEventListener('keydown', (ev) => {
        if (ev.key !== 'Escape') return;
        const open = $('ot-sky-card');
        if (open && !open.hidden && open.querySelector('button')) open.querySelector('button').click();
        else $('gx-back').click();
    });

    // ---- 🌌 the galaxy
    const G = D.galaxy;
    const sky = $('ot-sky');
    if (G && sky) galaxy(G, sky);

    function galaxy(G, sky) {
        const canvas = $('ot-canvas'), ctx = canvas.getContext('2d');
        const card = $('ot-sky-card'), loading = $('ot-loading');
        const n = G.n;
        const BG = [20, 20, 42];
        const hex = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
        const topicRGB = G.topics.map((t) => hex(t.ink));
        // by day: old blue to pink to new yellow
        const RAMP = ['#3a86ff', '#ff4fa3', '#ffc400'].map(hex);
        const rampAt = (f) => {
            const s = f * (RAMP.length - 1), k = Math.min(RAMP.length - 2, Math.floor(s)), u = s - k;
            return RAMP[k].map((v, j) => v + (RAMP[k + 1][j] - v) * u);
        };
        const dayRGB = DAYS.map((_, i) => rampAt(N > 1 ? i / (N - 1) : 1));
        const state = {color: 'topic', topic: null, until: null, hover: -1, chosen: -1};
        let X, Y, DAY, TOP, cellStart, order;
        const CELLS = 256;
        const view = {s: 1, ox: 0, oy: 0, w: 0, h: 0, dpr: 1};
        let image = null, acc = null, labelBoxes = [];

        fetch(`galaxy/points.bin?v=${encodeURIComponent(G.stamp)}`).then((r) => {
            if (!r.ok) throw new Error(r.status);
            return r.arrayBuffer();
        }).then((buf) => {
            const q = (k) => new Uint16Array(buf, 2 * k * n, n);
            X = new Float32Array(n); Y = new Float32Array(n);
            const qx = q(0), qy = q(1);
            for (let i = 0; i < n; i++) { X[i] = qx[i] / 65535; Y[i] = qy[i] / 65535; }
            DAY = q(2); TOP = new Uint8Array(buf, 6 * n, n);
            // a grid of cells, each listing its points, for finding the one under the pointer
            const cell = new Int32Array(n);
            cellStart = new Int32Array(CELLS * CELLS + 1);
            for (let i = 0; i < n; i++) {
                const c = Math.min(CELLS - 1, X[i] * CELLS | 0) * CELLS + Math.min(CELLS - 1, Y[i] * CELLS | 0);
                cell[i] = c; cellStart[c + 1]++;
            }
            for (let c = 0; c < CELLS * CELLS; c++) cellStart[c + 1] += cellStart[c];
            const fill = cellStart.slice(0, -1);
            order = new Int32Array(n);
            for (let i = 0; i < n; i++) order[fill[cell[i]]++] = i;
            loading.hidden = true;
            fit();
            draw();
        }).catch(() => { loading.textContent = '🦗 The galaxy couldn’t load. Try again in a moment.'; });

        // ---- controls
        const slider = $('ot-slider'), weekLabel = $('ot-week-label'), allBtn = $('ot-all'), playBtn = $('ot-play');
        slider.max = String(Math.max(0, N - 1));
        slider.value = String(Math.max(0, N - 1));
        const setUntil = (v) => {
            state.until = v;
            allBtn.setAttribute('aria-pressed', v === null ? 'true' : 'false');
            if (v === null) weekLabel.textContent = 'all of it';
            else weekLabel.textContent = `${dayName(DAYS[Math.max(0, v - 6)])} to ${dayName(DAYS[v])}`;
            draw();
        };
        slider.addEventListener('input', () => { stop(); setUntil(+slider.value); });
        allBtn.addEventListener('click', () => { stop(); setUntil(null); });
        let timer = null;
        const stop = () => { if (timer) { clearInterval(timer); timer = null; playBtn.textContent = '▶️ play'; } };
        playBtn.addEventListener('click', () => {
            if (timer) { stop(); return; }
            let v = state.until === null || state.until >= N - 1 ? Math.min(6, N - 1) : state.until + 1;
            slider.value = String(v); setUntil(v);
            playBtn.textContent = '⏸️ pause';
            timer = setInterval(() => {
                if (v >= N - 1) { stop(); return; }
                v += 1; slider.value = String(v); setUntil(v);
            }, reduced ? 1200 : 450);
        });
        document.querySelectorAll('[data-color]').forEach((b) => b.addEventListener('click', () => {
            state.color = b.dataset.color;
            document.querySelectorAll('[data-color]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
            topicsKey();
            draw();
        }));
        const topicList = $('ot-topics');
        function topicsKey() {
            if (state.color === 'day') {
                topicList.innerHTML = `<li><button type="button" disabled><span class="ot-dot" style="background:linear-gradient(90deg,#3a86ff,#ff4fa3,#ffc400);width:48px;border-radius:6px"></span>` +
                    `${dayName(DAYS[0])} → ${dayName(DAYS[N - 1])}</button></li>`;
                return;
            }
            topicList.innerHTML = G.topics.map((t, k) => `<li><button type="button" data-topic="${k}" aria-pressed="${state.topic === k}">` +
                `<span class="ot-dot" style="background:${t.ink}"></span>${esc(t.name)} <small>${t.n.toLocaleString()}</small></button></li>`).join('');
            topicList.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
                const k = +b.dataset.topic;
                state.topic = state.topic === k ? null : k;
                topicsKey();
                draw();
            }));
        }
        topicsKey();

        // ---- the view
        function size() {
            const r = sky.getBoundingClientRect();
            view.dpr = Math.min(window.devicePixelRatio || 1, 1.5);
            view.w = Math.max(1, Math.round(r.width)); view.h = Math.max(1, Math.round(r.height));
            canvas.width = Math.round(view.w * view.dpr); canvas.height = Math.round(view.h * view.dpr);
            acc = new Float32Array(canvas.width * canvas.height * 3);
        }
        // The whole map in the room left between the header and the controls floating over the sky
        function fit() {
            size();
            const top = document.querySelector('.gx-top').getBoundingClientRect().bottom;
            const bottom = view.h - document.querySelector('.gx-panel').getBoundingClientRect().top;
            const room = Math.max(view.h * 0.5, view.h - top - bottom);
            view.s = Math.min(view.w, room) * 0.96;
            view.ox = (view.w - view.s) / 2;
            view.oy = Math.min(top, view.h - room) + (room - view.s) / 2;
        }
        const lit = (i) => (state.topic === null || TOP[i] === state.topic) &&
            (state.until === null || (DAY[i] <= state.until && DAY[i] > state.until - 7));

        // Each dot adds its color to its pixel; a pixel fills toward white as dots pile up, so knots glow
        function render() {
            if (!X) return;
            const W = canvas.width, H = canvas.height, d = view.dpr, s = view.s * d, ox = view.ox * d, oy = view.oy * d;
            acc.fill(0);
            const zoom = view.s / (Math.min(view.w, view.h) * 0.94);
            const r = zoom > 9 ? 1 : 0;  // dots grow to 3x3 pixels close up
            const a = Math.min(0.9, 0.28 * Math.sqrt(zoom)), dim = 0.03;
            const filtering = state.topic !== null || state.until !== null;
            for (let i = 0; i < n; i++) {
                const px = ox + X[i] * s | 0, py = oy + Y[i] * s | 0;
                if (px < r || py < r || px >= W - r || py >= H - r) continue;
                let c, alpha;
                if (filtering && !lit(i)) { c = [150, 150, 175]; alpha = dim; }
                else { c = state.color === 'day' ? dayRGB[DAY[i]] : topicRGB[TOP[i]]; alpha = filtering ? Math.max(a, 0.9) : a; }
                for (let dy = -r; dy <= r; dy++) {
                    for (let dx = -r; dx <= r; dx++) {
                        const p = ((py + dy) * W + px + dx) * 3;
                        acc[p] += c[0] * alpha; acc[p + 1] += c[1] * alpha; acc[p + 2] += c[2] * alpha;
                    }
                }
            }
            image = ctx.createImageData(W, H);
            const out = image.data;
            for (let p = 0, q = 0; q < out.length; p += 3, q += 4) {
                out[q] = BG[0] + (255 - BG[0]) * (1 - Math.exp(-acc[p] / 255));
                out[q + 1] = BG[1] + (255 - BG[1]) * (1 - Math.exp(-acc[p + 1] / 255));
                out[q + 2] = BG[2] + (255 - BG[2]) * (1 - Math.exp(-acc[p + 2] / 255));
                out[q + 3] = 255;
            }
        }
        // Labels for the big stories and sagas that sit together: more as you zoom in, none overlapping
        function overlay() {
            if (!image) return;
            ctx.putImageData(image, 0, 0);
            const d = view.dpr;
            ctx.save();
            ctx.scale(d, d);
            const zoom = view.s / (Math.min(view.w, view.h) * 0.94);
            const most = Math.round((view.w < 560 ? 6 : 12) * Math.sqrt(zoom));
            const font = view.w < 560 ? 12 : 13;
            ctx.font = `700 ${font}px 'Comic Neue', 'Comic Sans MS', cursive`;
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
            labelBoxes = [];
            for (const L of G.labels) {
                if (labelBoxes.length >= most) break;
                let x = view.ox + L.x * view.s;
                const y = view.oy + L.y * view.s;
                if (x < 0 || y < 0 || x > view.w || y > view.h) continue;
                if (state.until !== null && (L.days[1] < state.until - 6 || L.days[0] > state.until)) continue;  // not that week
                const words = short(L.name, view.w < 560 ? 24 : 34);
                const w = ctx.measureText(words).width + 10, h = font + 8;
                x = Math.max(w / 2 + 2, Math.min(view.w - w / 2 - 2, x));  // kept inside the sky
                const box = {a: x - w / 2, b: x + w / 2, c: y - h / 2, e: y + h / 2, L};
                if (labelBoxes.some((o) => box.a < o.b && box.b > o.a && box.c < o.e && box.e > o.c)) continue;
                labelBoxes.push(box);
                ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeText(words, x, y);
                ctx.fillStyle = '#fff'; ctx.fillText(words, x, y);
            }
            for (const [k, color] of [[state.chosen, '#ffc400'], [state.hover, '#fff']]) {
                if (k < 0) continue;
                ctx.beginPath();
                ctx.arc(view.ox + X[k] * view.s, view.oy + Y[k] * view.s, 7, 0, Math.PI * 2);
                ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.stroke();
                ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
            }
            ctx.restore();
        }
        let pending = false;
        function draw() {
            if (pending) return;
            pending = true;
            requestAnimationFrame(() => { pending = false; render(); overlay(); });
        }
        new ResizeObserver(() => {
            if (!X) return;
            const r = sky.getBoundingClientRect();
            if (Math.round(r.width) === view.w && Math.round(r.height) === view.h) return;
            const cx = (view.w / 2 - view.ox) / view.s, cy = (view.h / 2 - view.oy) / view.s, k = view.s / Math.min(view.w, view.h);
            size();
            view.s = k * Math.min(view.w, view.h);
            view.ox = view.w / 2 - cx * view.s; view.oy = view.h / 2 - cy * view.s;
            draw();
        }).observe(sky);

        // The headline nearest the pointer, within a few pixels, among those lit
        function pick(mx, my) {
            if (!X) return -1;
            const gx = (mx - view.ox) / view.s, gy = (my - view.oy) / view.s;
            const reach = 9 / view.s;
            const c0 = Math.max(0, Math.floor((gx - reach) * CELLS)), c1 = Math.min(CELLS - 1, Math.floor((gx + reach) * CELLS));
            const r0 = Math.max(0, Math.floor((gy - reach) * CELLS)), r1 = Math.min(CELLS - 1, Math.floor((gy + reach) * CELLS));
            const filtering = state.topic !== null || state.until !== null;
            let best = -1, bd = reach * reach;
            for (let cx = c0; cx <= c1; cx++) {
                for (let cy = r0; cy <= r1; cy++) {
                    const c = cx * CELLS + cy;
                    for (let k = cellStart[c]; k < cellStart[c + 1]; k++) {
                        const i = order[k];
                        if (filtering && !lit(i)) continue;
                        const dx = X[i] - gx, dy = Y[i] - gy, dd = dx * dx + dy * dy;
                        if (dd < bd) { bd = dd; best = i; }
                    }
                }
            }
            return best;
        }
        const chunks = new Map();
        function words(i) {
            const k = Math.floor(i / G.chunk);
            if (!chunks.has(k)) {
                chunks.set(k, fetch(`galaxy/t-${k}.json?v=${encodeURIComponent(G.stamp)}`).then((r) => r.json())
                    .catch(() => { chunks.delete(k); return null; }));
            }
            return chunks.get(k).then((rows) => (rows ? rows[i - k * G.chunk] : null));
        }
        const topicName = (i) => G.topics[TOP[i]] ? G.topics[TOP[i]].name : '';
        function hoverAt(ev) {
            const r = canvas.getBoundingClientRect();
            const i = pick(ev.clientX - r.left, ev.clientY - r.top);
            if (i !== state.hover) { state.hover = i; overlay(); }
            const label = labelAt(ev.clientX - r.left, ev.clientY - r.top);
            canvas.style.cursor = i >= 0 || (label && label.href) ? 'pointer' : '';
            if (i < 0) {
                if (label) showTip(`<b>${esc(label.name)}</b>${label.n.toLocaleString()} headlines${label.href ? ' · click for its page' : ''}`, ev.clientX, ev.clientY);
                else hideTip();
                return;
            }
            words(i).then((w) => {
                if (state.hover !== i || !w) return;
                showTip(`<b>${esc(w[0])}</b><span class="ot-faint">${esc(w[1])} · ${esc(w[2])}</span>` +
                    (w[3] ? `<br>🗞️ ${esc(w[3])}` : '') + `<br><span class="ot-faint">🎨 ${esc(topicName(i))}</span>`, ev.clientX, ev.clientY);
            });
        }
        function labelAt(x, y) {
            const b = labelBoxes.find((o) => x >= o.a && x <= o.b && y >= o.c && y <= o.e);
            return b ? b.L : null;
        }
        function choose(i) {
            state.chosen = i;
            overlay();
            if (i < 0) { card.hidden = true; return; }
            card.hidden = false;
            card.innerHTML = '<p>…</p>';
            words(i).then((w) => {
                if (state.chosen !== i) return;
                if (!w) { card.innerHTML = '<p>🦗 Couldn’t load this headline.</p><button type="button" aria-label="Close">✕</button>'; }
                else {
                    card.innerHTML = `<b>${esc(w[0])}</b><small>📰 ${esc(w[1])} · ${esc(w[2])} · 🎨 ${esc(topicName(i))}</small>` +
                        (w[3] ? `<small>🗞️ ${w[4] ? `<a href="${esc(w[4])}">${esc(w[3])}</a>` : esc(w[3])}</small>` : '') +
                        '<button type="button" aria-label="Close">✕</button>';
                }
                card.querySelector('button').addEventListener('click', () => choose(-1));
            });
        }

        // ---- pan, zoom and pinch
        const pointers = new Map();
        let drag = null, moved = false;
        function zoomAt(f, mx, my) {
            const base = Math.min(view.w, view.h) * 0.94;
            const s = Math.max(base * 0.6, Math.min(base * 400, view.s * f));
            f = s / view.s;
            view.ox = mx - (mx - view.ox) * f; view.oy = my - (my - view.oy) * f; view.s = s;
            draw();
        }
        canvas.addEventListener('wheel', (ev) => {
            ev.preventDefault();  // the map is the whole page: scrolling zooms it
            const r = canvas.getBoundingClientRect();
            zoomAt(Math.exp(-ev.deltaY * 0.0015), ev.clientX - r.left, ev.clientY - r.top);
        }, {passive: false});
        canvas.addEventListener('pointerdown', (ev) => {
            canvas.setPointerCapture(ev.pointerId);
            pointers.set(ev.pointerId, {x: ev.clientX, y: ev.clientY});
            moved = false;
            drag = {x: ev.clientX, y: ev.clientY, ox: view.ox, oy: view.oy};
            if (pointers.size === 2) {
                const [a, b] = [...pointers.values()];
                drag.pinch = Math.hypot(a.x - b.x, a.y - b.y);
            }
        });
        canvas.addEventListener('pointermove', (ev) => {
            if (!pointers.has(ev.pointerId)) { if (ev.pointerType === 'mouse') hoverAt(ev); return; }
            pointers.set(ev.pointerId, {x: ev.clientX, y: ev.clientY});
            if (pointers.size === 2 && drag && drag.pinch) {
                const [a, b] = [...pointers.values()];
                const dist = Math.hypot(a.x - b.x, a.y - b.y);
                const r = canvas.getBoundingClientRect();
                zoomAt(dist / drag.pinch, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
                drag.pinch = dist;
                moved = true;
                return;
            }
            if (!drag) return;
            const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
            if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
            if (moved) {
                canvas.classList.add('ot-dragging');
                hideTip();
                view.ox = drag.ox + dx; view.oy = drag.oy + dy;
                draw();
            }
        });
        const up = (ev) => {
            pointers.delete(ev.pointerId);
            canvas.classList.remove('ot-dragging');
            if (pointers.size) { const [a] = [...pointers.values()]; drag = {x: a.x, y: a.y, ox: view.ox, oy: view.oy}; return; }
            if (!moved && ev.type === 'pointerup') {
                const r = canvas.getBoundingClientRect();
                const x = ev.clientX - r.left, y = ev.clientY - r.top;
                const i = pick(x, y);
                const label = labelAt(x, y);
                if (i < 0 && label && label.href) { location.href = label.href; return; }
                choose(i);
                hideTip();
            }
            drag = null;
        };
        canvas.addEventListener('pointerup', up);
        canvas.addEventListener('pointercancel', up);
        canvas.addEventListener('pointerleave', (ev) => {
            if (ev.pointerType === 'mouse' && !pointers.size) { state.hover = -1; overlay(); hideTip(); }
        });
        $('ot-zin').addEventListener('click', () => zoomAt(1.6, view.w / 2, view.h / 2));
        $('ot-zout').addEventListener('click', () => zoomAt(1 / 1.6, view.w / 2, view.h / 2));
        $('ot-zreset').addEventListener('click', () => { fit(); draw(); });
    }
})();
