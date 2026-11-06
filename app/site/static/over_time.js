// The news over time (app/site/page_over_time.py): four charts drawn as SVG at the width they're given (the headline
// galaxy has a page of its own: static/galaxy.js), redrawn when it changes. Every chart shares one day axis: day i of D.days spans [i, i+1].
(() => {
    const D = JSON.parse(document.getElementById('ot-data').textContent);
    const DAYS = D.days || [];
    const N = DAYS.length;
    const INK = '#1f1f2e';
    const SVG = 'http://www.w3.org/2000/svg';
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
    const dayName = (d) => { const [, m, dd] = d.split('-'); return `${MONTHS[+m - 1]} ${+dd}`; };
    const weekday = (d) => { const [y, m, dd] = d.split('-').map(Number); return new Date(y, m - 1, dd).getDay(); };
    const short = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s);
    const pct = (v) => `${Math.round(100 * v)}%`;

    // ---- one floating card for every chart
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
    addEventListener('scroll', hideTip, {passive: true});

    function el(tag, attrs, parent, text) {
        const e = document.createElementNS(SVG, tag);
        for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null) e.setAttribute(k, v);
        if (text !== undefined) e.textContent = text;
        if (parent) parent.appendChild(e);
        return e;
    }
    function link(parent, href) { return href ? el('a', {href}, parent) : parent; }

    // The day axis: [x0, x1] across the record
    function dayAxis(x0, x1) {
        const x = (d) => x0 + (x1 - x0) * d / Math.max(N, 1);
        return {x, w: (x1 - x0) / Math.max(N, 1), x0, x1};
    }
    // Ticks a readable distance apart: every day, two days, or on Mondays every week or two
    function ticks(ax) {
        const room = (ax.x1 - ax.x0) / 64;
        const step = [1, 2, 7, 14, 28].find((s) => N / s <= room) || 28;
        const out = [];
        for (let i = 0; i < N; i++) {
            if (step < 7 ? i % step === 0 : weekday(DAYS[i]) === 1 && Math.round((i - firstMonday) / 7) % (step / 7) === 0) out.push(i);
        }
        return out;
    }
    const firstMonday = Math.max(0, DAYS.findIndex((d) => weekday(d) === 1));
    function grid(svg, ax, top, bottom, labels = true) {
        for (const i of ticks(ax)) {
            el('line', {x1: ax.x(i), x2: ax.x(i), y1: top, y2: bottom, class: 'ot-grid'}, svg);
            if (labels) el('text', {x: ax.x(i), y: bottom + 14, class: 'ot-tick', 'text-anchor': 'middle'}, svg, dayName(DAYS[i]));
        }
    }
    // Labels on up to `rows` rows above a chart, each on the first row it fits without touching another; returns the
    // row or -1 when it fits nowhere
    function placer(x0, x1, rows) {
        const placed = [];
        return (x, width) => {
            let left = x - width / 2;
            left = Math.max(x0, Math.min(left, x1 - width));
            for (let r = 0; r < rows; r++) {
                if (placed.every((p) => p.r !== r || left + width + 8 < p.a || left > p.b + 8)) {
                    placed.push({r, a: left, b: left + width});
                    return {row: r, left};
                }
            }
            return {row: -1, left};
        };
    }
    const textWidth = (s, size) => s.length * size * 0.55;

    // Eastern day of an hourly time (naive UTC ISO), as a fraction on the day axis
    const eastern = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', year: 'numeric', month: '2-digit',
        day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
    const dayIndex = new Map(DAYS.map((d, i) => [d, i]));
    function onAxis(iso) {
        const parts = Object.fromEntries(eastern.formatToParts(new Date(iso + 'Z')).map((p) => [p.type, p.value]));
        const i = dayIndex.get(`${parts.year}-${parts.month}-${parts.day}`);
        return i === undefined ? null : i + (+parts.hour + +parts.minute / 60) / 24;
    }
    const hourName = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', weekday: 'short', month: 'short',
        day: 'numeric', hour: 'numeric'});

    // Redraw each chart when its width changes
    function chart(id, draw) {
        const host = $(id);
        if (!host) return;
        let last = 0;
        const go = () => {
            const w = Math.round(host.clientWidth);
            if (!w || w === last) return;
            last = w;
            host.textContent = '';
            draw(host, w);
        };
        new ResizeObserver(go).observe(host);
        go();
        return () => { last = 0; go(); };
    }
    // A strip of hit areas, one a day, that shows a card while pointed at (or tapped)
    function dayHover(svg, ax, top, bottom, html, onDay) {
        const cross = el('line', {y1: top, y2: bottom, class: 'ot-cross', visibility: 'hidden'}, svg);
        const hit = el('rect', {x: ax.x0, y: top, width: ax.x1 - ax.x0, height: bottom - top, class: 'ot-hit'}, svg);
        const at = (ev) => {
            const r = svg.getBoundingClientRect();
            const scale = svg.viewBox.baseVal.width / r.width;
            const x = (ev.clientX - r.left) * scale;
            return Math.max(0, Math.min(N - 1, Math.floor((x - ax.x0) / ax.w)));
        };
        const move = (ev) => {
            const i = at(ev);
            const h = html(i, ev);
            if (!h) { hideTip(); cross.setAttribute('visibility', 'hidden'); return; }
            const cx = onDay ? onDay(i, ev) : ax.x(i + 0.5);
            cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
            showTip(h, ev.clientX, ev.clientY);
        };
        hit.addEventListener('pointermove', move);
        hit.addEventListener('pointerdown', move);
        hit.addEventListener('pointerleave', () => { hideTip(); cross.setAttribute('visibility', 'hidden'); });
        return hit;
    }

    // ---- 📈 newsiness: the hourly score, the big and normal lines, each story's peak above the big line
    chart('ot-newsiness-chart', (host, W) => {
        const S = D.newsiness;
        if (!S || S.points.length < 2) { host.innerHTML = '<p class="stage-empty">🦗 No scores yet.</p>'; return; }
        const narrow = W < 560;
        const rows = narrow ? 3 : 3, rowH = 16;
        const top = 10 + rows * rowH + 6, H = (narrow ? 250 : 320), bottom = H - 22, left = 30, right = W - 6;
        const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
            'aria-label': 'How newsy each hour was'}, host);
        const ax = dayAxis(left, right);
        const pts = S.points.map((p) => ({t: onAxis(p[0]), score: p[1], kept: p[2], story: S.stories[p[3]], outlets: p[4],
            active: p[5], at: p[0]})).filter((p) => p.t !== null);
        const hi = Math.max(0.8, Math.max(...pts.map((p) => p.score)) + 0.05);
        const y = (v) => bottom - (bottom - top) * v / hi;
        el('rect', {x: left, y: y(hi), width: right - left, height: y(S.big) - y(hi), class: 'ot-band-big'}, svg);
        el('rect', {x: left, y: y(S.big), width: right - left, height: y(S.normal) - y(S.big), class: 'ot-band-normal'}, svg);
        grid(svg, ax, top, bottom);
        for (const v of [0, 0.25, 0.5, 0.75]) {
            if (v <= hi) el('text', {x: left - 5, y: y(v) + 4, class: 'ot-tick', 'text-anchor': 'end'}, svg, String(v));
        }
        el('line', {x1: left, x2: right, y1: y(S.big), y2: y(S.big), class: 'ot-mark-line'}, svg);
        el('line', {x1: left, x2: right, y1: y(S.normal), y2: y(S.normal), class: 'ot-mark-line'}, svg);
        el('text', {x: left + 4, y: y(S.big) - 4, class: 'ot-note'}, svg, '🚨 big news day');
        el('text', {x: left + 4, y: y(S.normal) + 13, class: 'ot-note'}, svg, '📰 normal');
        // runs of hours with no gap over twelve hours (a missed build or two is bridged), each drawn dashed (worked
        // out afterwards) or solid (kept)
        const runs = [];
        pts.forEach((p, k) => {
            const prev = pts[k - 1];
            if (!prev || p.kept !== prev.kept || (p.t - prev.t) * 24 > 12) runs.push([]);
            runs[runs.length - 1].push(p);
        });
        for (const run of runs) {
            const line = run.map((p) => `${ax.x(p.t).toFixed(1)},${y(p.score).toFixed(1)}`).join(' ');
            if (run.length > 1) {
                el('polygon', {points: `${ax.x(run[0].t).toFixed(1)},${bottom} ${line} ${ax.x(run[run.length - 1].t).toFixed(1)},${bottom}`, class: 'ot-area'}, svg);
            }
            el('polyline', {points: line, class: 'ot-line', 'stroke-dasharray': run[0].kept ? null : '4 3'}, svg);
        }
        el('line', {x1: left, x2: right, y1: bottom, y2: bottom, class: 'ot-axis'}, svg);
        // the hover: the nearest hour
        const byTime = pts.map((p) => p.t);
        const nearest = (t) => {
            let lo = 0, hiI = byTime.length - 1;
            while (hiI - lo > 1) { const mid = (lo + hiI) >> 1; if (byTime[mid] < t) lo = mid; else hiI = mid; }
            return Math.abs(byTime[lo] - t) < Math.abs(byTime[hiI] - t) ? pts[lo] : pts[hiI];
        };
        let near = null;
        const dot = el('circle', {r: 4, fill: INK, visibility: 'hidden', 'pointer-events': 'none'}, svg);
        dayHover(svg, ax, top, bottom, (i, ev) => {
            const r = svg.getBoundingClientRect();
            const t = ((ev.clientX - r.left) * W / r.width - left) / ax.w;
            near = nearest(t);
            dot.setAttribute('cx', ax.x(near.t)); dot.setAttribute('cy', y(near.score)); dot.setAttribute('visibility', 'visible');
            return `<b>${esc(hourName.format(new Date(near.at + 'Z')))} ET: ${near.score.toFixed(2)}</b>` +
                `Top story: ${esc(near.story)}<br><span class="ot-faint">${near.outlets} of ${near.active} outlets` +
                `${near.kept ? '' : ', worked out afterwards'}</span>`;
        }, () => ax.x(near.t));
        svg.addEventListener('pointerleave', () => dot.setAttribute('visibility', 'hidden'));
        // the spikes: the highest first gets the first room for its label
        const place = placer(left, right, rows);
        const size = 12, chars = narrow ? 24 : 40;
        const order = [...S.spikes].sort((a, b) => b.score - a.score);
        for (const s of order) {
            const t = onAxis(s.at);
            if (t === null) continue;
            const x = ax.x(t), yy = y(s.score);
            const words = short(s.label, chars);
            const spot = place(x, textWidth(words, size));
            const g = el('g', {}, svg);
            if (spot.row >= 0) {
                const ty = 10 + spot.row * rowH + 11;
                el('line', {x1: x, x2: x, y1: ty + 3, y2: yy - 6, class: 'ot-stem'}, g);
                el('text', {x: spot.left, y: ty, class: 'ot-label'}, link(g, s.href), words);
            }
            const c = el('circle', {cx: x, cy: yy, r: 5, class: 'ot-spike'}, link(g, s.href));
            const card = `<b>${esc(s.label)}</b>${esc(hourName.format(new Date(s.at + 'Z')))} ET: ${s.score.toFixed(2)}` +
                `<br><span class="ot-faint">${s.outlets} of ${s.active} outlets${s.href ? ' · tap for its story' : ''}</span>`;
            c.addEventListener('pointerenter', (ev) => showTip(card, ev.clientX, ev.clientY));
            c.addEventListener('pointerleave', hideTip);
        }
    });

    // Rows of day bars (the tides) or ribbons (the sagas), one scale for all rows but the first when `ownFirst`
    function rowsChart(host, W, items, opts) {
        const nameH = 18, bandH = opts.ribbon ? 26 : 34, gap = 10;
        const rowH = nameH + bandH + gap;
        const top = 4, left = 6, right = W - 6;
        const H = top + rowH * items.length + 18;
        const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': opts.label}, host);
        const ax = dayAxis(left, right);
        grid(svg, ax, top, H - 18);
        const shared = Math.max(1, ...items.filter((it, k) => !(opts.ownFirst && k === 0)).flatMap((it) => it.counts));
        const scale = opts.sqrt ? Math.sqrt : (v) => v;
        items.forEach((it, k) => {
            const y0 = top + k * rowH, band = y0 + nameH, mid = band + bandH / 2;
            const most = opts.ownFirst && k === 0 ? Math.max(1, ...it.counts) : shared;
            const peakDay = it.peak && it.peak.n ? DAYS.indexOf(it.peak.day) : -1;
            // on a phone the name gets the room: only the biggest day beside it
            const peakWords = peakDay >= 0 ? `▲ ${dayName(it.peak.day)}: ${it.peak.n}` : '';
            const side = W < 560 ? peakWords + (it.narrow ? ` · ${it.narrow}` : '') : [peakWords, it.side].filter(Boolean).join(' · ');
            const room = right - left - textWidth(side, 11) - 14;
            el('text', {x: left, y: y0 + 13, class: 'ot-name'}, link(svg, it.href), short(it.title, Math.max(8, Math.floor(room / (13 * 0.55)))));
            el('text', {x: right, y: y0 + 13, class: 'ot-note', 'text-anchor': 'end'}, svg, side);
            const ink = it.ink || '#fff';
            if (opts.ribbon) {
                const on = it.counts.map((c, i) => (c ? i : -1)).filter((i) => i >= 0);
                if (on.length) el('line', {x1: ax.x(on[0] + 0.5), x2: ax.x(on[on.length - 1] + 0.5), y1: mid, y2: mid, stroke: INK, 'stroke-width': 1.5}, svg);
            } else {
                el('line', {x1: left, x2: right, y1: band + bandH, y2: band + bandH, class: 'ot-axis'}, svg);
            }
            it.counts.forEach((c, i) => {
                if (!c) return;
                const h = Math.max(opts.ribbon ? 3 : 2, bandH * scale(c) / scale(most));
                const x = ax.x(i) + (ax.w > 4 ? 0.75 : 0), w = Math.max(1, ax.w - (ax.w > 4 ? 1.5 : 0));
                el('rect', {x, y: opts.ribbon ? mid - h / 2 : band + bandH - h, width: w, height: h, rx: ax.w > 6 ? 2 : 0,
                    fill: ink, stroke: INK, 'stroke-width': i === peakDay ? 2 : 0.6}, svg);
            });
            // a hover area across the row: that day's count
            const hit = el('rect', {x: left, y: band, width: right - left, height: bandH, class: 'ot-row-hit'}, svg);
            const move = (ev) => {
                const r = svg.getBoundingClientRect();
                const i = Math.max(0, Math.min(N - 1, Math.floor(((ev.clientX - r.left) * W / r.width - left) / ax.w)));
                showTip(`<b>${esc(it.title)}</b>${dayName(DAYS[i])}: ${it.counts[i]} ${opts.unit(it.counts[i])}` +
                    `<br><span class="ot-faint">${esc(it.total)} in all</span>` +
                    (it.href ? '<br><span class="ot-faint">tap the name for its page</span>' : ''), ev.clientX, ev.clientY);
            };
            hit.addEventListener('pointermove', move);
            hit.addEventListener('pointerdown', move);
            hit.addEventListener('pointerleave', hideTip);
        });
        return svg;
    }

    // ---- 🧶 motif tides: every claim filed, then the motifs told most in a week, a row each on one scale
    chart('ot-tides-chart', (host, W) => {
        const T = D.tides;
        if (!T || !T.motifs.length) { host.innerHTML = '<p class="stage-empty">🦗 No motif has claims in our record yet.</p>'; return; }
        const items = [{title: '🧩 Every claim filed, all motifs', counts: T.all, ink: '#c8f7e6', side: `${T.claims.toLocaleString()} claims · own scale`, narrow: 'own scale', total: `${T.claims.toLocaleString()} claims`,
            peak: {day: DAYS[T.all.indexOf(Math.max(...T.all))], n: Math.max(...T.all)}}]
            .concat(T.motifs.map((m) => ({title: `${m.emoji} ${m.name}`, counts: m.counts, ink: m.ink, href: m.href, peak: m.peak,
                side: `${m.total} claim${m.total === 1 ? '' : 's'}`, total: `${m.total} claim${m.total === 1 ? '' : 's'}`})));
        rowsChart(host, W, items, {label: 'Claims filed under the motifs told most, day by day', ownFirst: true,
            unit: (n) => (n === 1 ? 'claim' : 'claims')});
    });

    // ---- 🧵 saga lifelines
    chart('ot-sagas-chart', (host, W) => {
        const S = D.sagas;
        if (!S || !S.length) { host.innerHTML = '<p class="stage-empty">🦗 No saga yet.</p>'; return; }
        rowsChart(host, W, S.map((s) => ({title: `🧵 ${s.name}`, counts: s.counts, ink: s.ink, href: s.href, peak: s.peak,
            side: `${s.total.toLocaleString()} headlines`, total: `${s.total.toLocaleString()} headlines`})), {label: 'The biggest sagas, headlines a day', ribbon: true, sqrt: true,
            unit: (n) => (n === 1 ? 'headline first seen' : 'headlines first seen')});
    });

    // ---- 😱 feelings: each day's vote stacked to 100%, the days a feeling ran high pinned with their story
    const E = D.emotions;
    if (E && $('ot-feelings-key')) {
        $('ot-feelings-key').innerHTML = [...E.feelings].reverse().map((f) => `<li><span class="ot-swatch" style="background:${E.ink[f]}"></span>` +
            `${E.emoji[f]} ${f === 'neutral' ? 'no strong feeling' : f}</li>`).join('');
    }
    let feelingsView = 'stack';
    const feelingsChart = chart('ot-feelings-chart', (host, W) => {
        if (!E || !E.counts.some((c) => c)) { host.innerHTML = '<p class="stage-empty">🦗 No feelings read yet.</p>'; return; }
        if (feelingsView === 'rows') { feelingRows(host, W); return; }
        const narrow = W < 560;
        const rows = 3, rowH = 16;
        const top = 10 + rows * rowH + 6, H = narrow ? 280 : 340, bottom = H - 22, left = 34, right = W - 6;
        const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
            'aria-label': 'Each day\'s headlines by the feelings they stir, stacked to 100%'}, host);
        const ax = dayAxis(left, right);
        const y = (v) => bottom - (bottom - top) * v;
        const have = E.counts.map((c, i) => (E.shares[E.feelings[0]][i] !== null ? i : -1)).filter((i) => i >= 0);
        const below = new Map(have.map((i) => [i, 0]));
        const xs = (i, k) => (k === 0 ? ax.x(i) : k === have.length - 1 ? ax.x(i + 1) : ax.x(i + 0.5));
        const tops = {};
        for (const f of E.feelings) {
            const upper = have.map((i) => below.get(i) + (E.shares[f][i] || 0));
            const pts = have.map((i, k) => `${xs(i, k).toFixed(1)},${y(upper[k]).toFixed(1)}`);
            const back = have.map((i, k) => `${xs(i, k).toFixed(1)},${y(below.get(i)).toFixed(1)}`).reverse();
            el('polygon', {points: pts.concat(back).join(' '), fill: E.ink[f], stroke: '#fff', 'stroke-width': 1}, svg);
            tops[f] = new Map(have.map((i, k) => [i, [below.get(i), upper[k]]]));
            have.forEach((i, k) => below.set(i, upper[k]));
        }
        grid(svg, ax, top, bottom);
        for (const v of [0, 0.5, 1]) el('text', {x: left - 5, y: y(v) + 4, class: 'ot-tick', 'text-anchor': 'end'}, svg, pct(v));
        el('line', {x1: left, x2: right, y1: bottom, y2: bottom, class: 'ot-axis'}, svg);
        const pins = new Map((E.spikes || []).map((s) => [s.day, s]));
        dayHover(svg, ax, top, bottom, (i) => {
            if (E.shares[E.feelings[0]][i] === null) return null;
            const list = E.feelings.map((f) => [f, E.shares[f][i] || 0]).sort((a, b) => b[1] - a[1])
                .map(([f, v]) => `<li><span>${E.emoji[f]} ${f === 'neutral' ? 'no strong feeling' : f}</span><span>${pct(v)}</span></li>`).join('');
            const pin = pins.get(DAYS[i]);
            return `<b>${dayName(DAYS[i])}${DAYS[i] === D.today ? ' (so far)' : ''}: ${E.counts[i].toLocaleString()} news headlines</b><ul>${list}</ul>` +
                (pin && pin.label ? `<span class="ot-faint">${pin.emoji} ${esc(pin.feeling)} ran high: ${esc(pin.label)}</span>` : '');
        });
        const place = placer(left, right, rows);
        const chars = narrow ? 22 : 38;
        for (const s of [...(E.spikes || [])].sort((a, b) => b.lift - a.lift)) {
            const i = DAYS.indexOf(s.day);
            if (i < 0 || !tops[s.feeling].has(i)) continue;
            const [lo, hiV] = tops[s.feeling].get(i);
            const x = ax.x(i + 0.5), yy = y((lo + hiV) / 2);
            const words = `${s.emoji} ${short(s.label || s.feeling, chars)}`;
            const spot = place(x, textWidth(words, 12) + 8);
            const g = el('g', {}, svg);
            if (spot.row >= 0) {
                const ty = 10 + spot.row * rowH + 11;
                el('line', {x1: x, x2: x, y1: ty + 3, y2: yy, class: 'ot-stem'}, g);
                el('text', {x: spot.left, y: ty, class: 'ot-label'}, link(g, s.href), words);
            }
            const c = el('circle', {cx: x, cy: yy, r: 5, fill: '#fff', stroke: INK, 'stroke-width': 2}, link(g, s.href));
            const card = `<b>${s.emoji} ${esc(s.feeling)} on ${dayName(s.day)}: ${pct(s.share)} (usually ${pct(s.usual)})</b>` +
                (s.label ? `Its biggest story among the headlines ${esc(s.feeling)} led: ${esc(s.label)} (${s.headlines} headlines)` : '');
            c.addEventListener('pointerenter', (ev) => showTip(card, ev.clientX, ev.clientY));
            c.addEventListener('pointerleave', hideTip);
        }
    });

    document.querySelectorAll('[data-feelings]').forEach((b) => b.addEventListener('click', () => {
        feelingsView = b.dataset.feelings;
        document.querySelectorAll('[data-feelings]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
        if (feelingsChart) feelingsChart();
    }));
    // Each feeling on its own scale, lowest day to highest, its usual (median) day dashed
    function feelingRows(host, W) {
        const nameH = 16, bandH = 34, gap = 10, rowH = nameH + bandH + gap, left = 6, right = W - 6, top = 4;
        const list = E.feelings.filter((f) => f !== 'neutral').concat(['neutral']);
        const H = top + rowH * list.length + 18;
        const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
            'aria-label': 'Each feeling\'s share of the day\'s headlines, each on its own scale'}, host);
        const ax = dayAxis(left, right);
        grid(svg, ax, top, H - 18);
        const pins = new Map((E.spikes || []).map((s) => [`${s.day} ${s.feeling}`, s]));
        list.forEach((f, k) => {
            const y0 = top + k * rowH, band = y0 + nameH;
            const vals = E.shares[f];
            const have = vals.filter((v) => v !== null);
            if (!have.length) return;
            const lo = Math.min(...have), hi = Math.max(...have), sorted = [...have].sort((a, b) => a - b);
            const usual = sorted[Math.floor(sorted.length / 2)];
            const y = (v) => band + bandH - (bandH - 4) * (v - lo) / Math.max(hi - lo, 1e-6) - 2;
            el('text', {x: left, y: y0 + 12, class: 'ot-name'}, svg, `${E.emoji[f]} ${f === 'neutral' ? 'no strong feeling' : f}`);
            el('text', {x: right, y: y0 + 12, class: 'ot-note', 'text-anchor': 'end'}, svg, `${pct(lo)} to ${pct(hi)} · usually ${pct(usual)}`);
            el('line', {x1: left, x2: right, y1: y(usual), y2: y(usual), stroke: '#999', 'stroke-dasharray': '3 3'}, svg);
            const pts = vals.map((v, i) => (v === null ? null : `${ax.x(i + 0.5).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
            const ink = f === 'neutral' ? '#8a8f98' : E.ink[f];
            el('polyline', {points: pts.join(' '), fill: 'none', stroke: INK, 'stroke-width': 4, 'stroke-linejoin': 'round'}, svg);
            el('polyline', {points: pts.join(' '), fill: 'none', stroke: ink, 'stroke-width': 2.5, 'stroke-linejoin': 'round'}, svg);
            const hit = el('rect', {x: left, y: band, width: right - left, height: bandH, class: 'ot-row-hit'}, svg);
            const move = (ev) => {
                const r = svg.getBoundingClientRect();
                const i = Math.max(0, Math.min(N - 1, Math.floor(((ev.clientX - r.left) * W / r.width - left) / ax.w)));
                if (vals[i] === null) { hideTip(); return; }
                const pin = pins.get(`${DAYS[i]} ${f}`);
                showTip(`<b>${E.emoji[f]} ${f === 'neutral' ? 'no strong feeling' : f} on ${dayName(DAYS[i])}: ${pct(vals[i])}</b>` +
                    `usually ${pct(usual)} · ${E.counts[i].toLocaleString()} news headlines` +
                    (pin && pin.label ? `<br><span class="ot-faint">its biggest story that day: ${esc(pin.label)}</span>` : ''), ev.clientX, ev.clientY);
            };
            hit.addEventListener('pointermove', move);
            hit.addEventListener('pointerdown', move);
            hit.addEventListener('pointerleave', hideTip);
            vals.forEach((v, i) => {  // over the hover strip, so they can be tapped
                const pin = pins.get(`${DAYS[i]} ${f}`);
                if (v === null || !pin) return;
                el('circle', {cx: ax.x(i + 0.5), cy: y(v), r: 5, fill: '#fff', stroke: INK, 'stroke-width': 2}, link(svg, pin.href));
            });
        });
    }
})();
