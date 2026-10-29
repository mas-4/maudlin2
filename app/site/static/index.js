const bias = {
    '-3': 'Extreme Left',
    '-2': 'Left',
    '-1': 'Left Center',
    '0': 'Unbiased',
    '1': 'Right Center',
    '2': 'Right',
    '3': 'Extreme Right'
};
const credibility = {'0': 'Very Low', '1': 'Low', '2': 'Mixed', '3': 'Mostly Factual', '4': 'High', '5': 'Very High'};

function determineSmiley(value, bias) {
    if (value > bias) {
        return '😊';
    } else if (value < -bias) {
        return '😭';
    }
    return '';
}

function recenter(value, bias, range) {
    return (value + bias) / (range * bias);
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function getColorForValue(value, bias, range) {
    if (value === 'N/A')
        return 'white';
    if (value == null)
        return '#f9fafb';

    let a = recenter(value, bias, range);
    let b = 120 * a;
    let c = clamp(b, 0, 120);

    // Return a CSS HSL string
    return 'hsl(' + c + ', 100%, 50%)';
}

function nacompare(a, b) {
    if (a === 'N/A')
        return 1;
    if (b === 'N/A')
        return -1;
    if (a > b) {
        return 1;
    } else if (b > a) {
        return -1;
    } else {
        return 0;
    }
}
// Pop a card up over the page at a jaunty angle, with a button to jump to where it lives. Used for outlet cards
// (from the lineup) and story cards (from the headline table's 📌).
function closePop() {
    document.querySelector('.pop-backdrop')?.remove();
}

function popCard(card) {
    if (!card) return;
    closePop();
    const backdrop = document.createElement('div');
    backdrop.className = 'pop-backdrop';
    const pop = card.cloneNode(true);
    pop.removeAttribute('id');
    pop.classList.add('pop-card');
    pop.style.setProperty('--tilt', `${(Math.random() < 0.5 ? -1 : 1) * (2 + Math.random() * 4)}deg`);
    const actions = document.createElement('div');
    actions.className = 'pop-actions';
    actions.innerHTML = '<button type="button" class="pop-jump">jump to it ↓</button>'
        + '<button type="button" class="pop-close" aria-label="Close">✕</button>';
    pop.appendChild(actions);
    backdrop.appendChild(pop);
    document.body.appendChild(backdrop);
    backdrop.addEventListener('click', (ev) => { if (ev.target === backdrop) closePop(); });
    actions.querySelector('.pop-close').addEventListener('click', closePop);
    actions.querySelector('.pop-jump').addEventListener('click', () => {
        closePop();
        card.scrollIntoView({behavior: 'smooth', block: 'center'});
        card.classList.add('flash');
        setTimeout(() => card.classList.remove('flash'), 1800);
    });
}

document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') closePop(); });

// Pack cards into as many columns as fit (each at least `minWidth` px), every card dropping into the shortest column,
// so short cards never leave a hole beside a long one. Returns a function to repack with a new list of cards (after a
// sort or a search). Cards keep their ids, so #links still land.
function packColumns(box, cards, minWidth, maxColumns = Infinity) {
    let current = cards, count = 0;
    function layout(next, force) {
        if (next) current = next;
        const n = Math.max(1, Math.min(maxColumns, Math.floor(box.clientWidth / minWidth)));
        if (n === count && !force && !next) return;
        count = n;
        box.style.minHeight = box.offsetHeight + 'px';  // hold the height while repacking, so the page doesn't jump
        box.classList.add('packed');
        const columns = Array.from({length: n}, () => {
            const col = document.createElement('div');
            col.className = 'packed-column';
            return col;
        });
        box.replaceChildren(...columns);
        for (const card of current) {
            columns.reduce((a, b) => b.offsetHeight < a.offsetHeight ? b : a).appendChild(card);
        }
        box.style.minHeight = '';
    }
    layout(null, true);
    addEventListener('resize', () => layout());
    return (next) => layout(next, true);
}

// Tables with class "sortable": click a column header to sort, again to reverse. A header with data-sort="number"
// sorts by its cells' data-value; text sorts ignore case and a leading "The " (livemint.com among the Ls, The Week
// among the Ws). Tables that collapse ("collapsed" class) keep their first rows showing after a sort.
const TEXT_ORDER = new Intl.Collator('en', {sensitivity: 'base', numeric: true});
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('table.sortable').forEach((table) => {
        table.querySelectorAll('thead th').forEach((th, col) => {
            let descending = th.dataset.sort === 'number';  // numbers biggest first, names A to Z
            th.addEventListener('click', () => {
                const rows = [...table.tBodies[0].rows];
                const numeric = th.dataset.sort === 'number';
                const key = (row) => numeric
                    ? parseFloat(row.cells[col].dataset.value) : row.cells[col].textContent.trim().replace(/^the\s+/i, '');
                const order = (a, b) => numeric ? (a > b ? 1 : a < b ? -1 : 0) : TEXT_ORDER.compare(a, b);
                rows.sort((a, b) => order(key(a), key(b)) * (descending ? -1 : 1));
                descending = !descending;
                rows.forEach((row) => table.tBodies[0].appendChild(row));
            });
        });
    });
});

// Ambient 90s geometry behind every page, Memphis style: big shapes in teal, magenta, purple and yellow with thick black
// outlines and hard offset shadows (like the cards), parked half off the window's edges so they frame the page, plus
// a sprinkle of tiny terrazzo flecks. Each shape turns and bobs on its own clock (style.css); a new layout every load
(function memphis() {
    const INK = '#1f1f2e';
    const COLORS = ['#1fc7b6', '#ff3ea5', '#8a5cff', '#ffd21f'];
    const pick = (list) => list[Math.floor(Math.random() * list.length)];
    const rand = (a, b) => a + Math.random() * (b - a);
    // A filled shape: black shadow offset down-right, then the color with a black outline
    const solid = (d, c) => `<path d="${d}" fill="${INK}" transform="translate(6 6)"/>`
        + `<path d="${d}" fill="${c}" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>`;
    // A line shape: shadow, black casing, then the color down the middle
    const line = (d, c, w = 9) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${w + 7}" stroke-linecap="round" stroke-linejoin="round" transform="translate(5 5)"/>`
        + `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${w + 7}" stroke-linecap="round" stroke-linejoin="round"/>`
        + `<path d="${d}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
    const SHAPES = [
        // lightning bolt
        (c) => solid('M58 4 L22 56 L46 56 L36 96 L80 38 L54 38 Z', c),
        // squiggle
        (c) => line('M4 50 q12 -26 24 0 t24 0 t24 0 t24 0', c),
        // zigzag
        (c) => line('M4 64 l16 -28 l16 28 l16 -28 l16 28 l16 -28', c),
        // plain black squiggle, the era's signature
        () => `<path d="M6 50 C22 14 34 86 50 50 S78 14 94 50" fill="none" stroke="${INK}" stroke-width="9" stroke-linecap="round"/>`,
        // triangle
        (c) => solid('M50 8 L92 84 L8 84 Z', c),
        // checkerboard square
        (c) => `<rect x="16" y="16" width="70" height="70" fill="${INK}" transform="translate(6 6)"/>`
            + `<rect x="16" y="16" width="70" height="70" fill="white" stroke="${INK}" stroke-width="4"/>`
            + [0, 1, 2, 3, 4].map((i) => [0, 1, 2, 3, 4].filter((j) => (i + j) % 2 === 0)
                .map((j) => `<rect x="${16 + i * 14}" y="${16 + j * 14}" width="14" height="14" fill="${INK}"/>`).join('')).join(''),
        // halftone circle: dots that grow toward one side
        (c) => `<circle cx="50" cy="50" r="38" fill="${INK}" transform="translate(6 6)"/>`
            + `<circle cx="50" cy="50" r="38" fill="${c}" stroke="${INK}" stroke-width="4"/>`
            + `<clipPath id="ht"><circle cx="50" cy="50" r="36"/></clipPath><g clip-path="url(#ht)" fill="${INK}">`
            + [...Array(7).keys()].map((i) => [...Array(7).keys()].map((j) =>
                `<circle cx="${17 + i * 11}" cy="${17 + j * 11}" r="${(0.4 + i * 0.55).toFixed(1)}"/>`).join('')).join('') + '</g>',
        // flat-shaded cylinder
        (c) => `<path d="M24 26 v50 a26 10 0 0 0 52 0 v-50" fill="${INK}" transform="translate(6 6)"/>`
            + `<path d="M24 26 v50 a26 10 0 0 0 52 0 v-50" fill="${c}" stroke="${INK}" stroke-width="4"/>`
            + `<path d="M58 30 v48" stroke="white" stroke-width="5" opacity="0.6"/>`
            + `<ellipse cx="50" cy="26" rx="26" ry="10" fill="white" stroke="${INK}" stroke-width="4"/>`,
        // half circle
        (c) => solid('M8 66 a42 42 0 0 1 84 0 Z', c),
        // ring
        (c) => `<circle cx="50" cy="50" r="32" fill="none" stroke="${INK}" stroke-width="18" transform="translate(5 5)"/>`
            + `<circle cx="50" cy="50" r="32" fill="none" stroke="${INK}" stroke-width="18"/>`
            + `<circle cx="50" cy="50" r="32" fill="none" stroke="${c}" stroke-width="10"/>`,
    ];
    const FLECKS = [
        (c) => `<path d="M2 9 L6 2 L10 9 Z" fill="${c}"/>`,
        (c) => `<path d="M2 6 h8" stroke="${c}" stroke-width="2.5" stroke-linecap="round"/>`,
        (c) => `<circle cx="6" cy="6" r="2.6" fill="${c}"/>`,
        (c) => `<path d="M1 7 q2.5 -4 5 0 t5 0" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round"/>`,
    ];
    const sprite = (inner, size, x, y, extra) => {
        const style = `left: ${x}; top: ${y}; --tilt: ${Math.round(rand(-60, 60))}deg; --dur: ${Math.round(rand(50, 140))}s;`
            + ` --dir: ${Math.random() < 0.5 ? 'normal' : 'reverse'}; --dx: ${Math.round(rand(-30, 30))}px;`
            + ` --dy: ${Math.round(rand(-30, 30))}px; animation-delay: -${Math.round(rand(0, 60))}s;${extra || ''}`;
        return `<svg viewBox="0 0 ${size.box} ${size.box}" width="${size.px}" height="${size.px}" style="${style}">${inner}</svg>`;
    };
    function draw() {
        const W = window.innerWidth, H = window.innerHeight;
        const phone = W < 700;
        let html = '';
        // Big shapes along the edges, about half off the window, spaced down each side
        const big = phone ? 5 : 9;
        for (let i = 0; i < big; i++) {
            const px = Math.round(phone ? rand(90, 130) : rand(120, 200));
            const side = i % 2 === 0 ? 'left' : 'right';
            const slot = (Math.floor(i / 2) + rand(0.15, 0.85)) / Math.ceil(big / 2);
            const x = side === 'left' ? `${-px * rand(0.35, 0.6)}px` : `calc(100% - ${px * rand(0.4, 0.65)}px)`;
            html += sprite(pick(SHAPES)(pick(COLORS)), {box: 100, px}, x, `calc(${(slot * 100).toFixed(1)}% - ${px / 2}px)`);
        }
        // Terrazzo flecks scattered everywhere, small and lighter
        const flecks = Math.round(W * H / (phone ? 14000 : 20000));
        for (let i = 0; i < flecks; i++) {
            const px = Math.round(rand(10, 20));
            html += sprite(pick(FLECKS)(pick([...COLORS, INK])), {box: 12, px}, `${rand(0, 100).toFixed(1)}%`,
                `${rand(0, 100).toFixed(1)}%`, ' opacity: 0.4;');
        }
        const layer = document.createElement('div');
        layer.id = 'memphis';
        layer.setAttribute('aria-hidden', 'true');
        layer.innerHTML = html;
        document.body.prepend(layer);
    }
    if (document.body) draw(); else document.addEventListener('DOMContentLoaded', draw);
})();

// Share: a 🔗 on each card copies a link straight to it. Story cards use their saved story's id (data-share, "s-123"),
// which lasts across runs, where the card's own id is the hour's cluster number; other cards use their id. Opening
// such a link scrolls to the card once the page has laid its cards out.
document.addEventListener('DOMContentLoaded', () => {
    const copy = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
        } catch (e) {  // no clipboard API outside https (the local preview): the old way
            const area = Object.assign(document.createElement('textarea'), {value: text});
            document.body.appendChild(area);
            area.select();
            document.execCommand('copy');
            area.remove();
        }
    };
    document.querySelectorAll('.story, .court-story[id], .outlet-card[id]').forEach((card) => {
        const anchor = card.dataset.share || card.id;
        if (!anchor) return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'share-link';
        button.title = 'Copy a link to this';
        button.setAttribute('aria-label', 'Copy a link to this');
        button.textContent = '🔗';
        button.dataset.anchor = anchor;
        card.prepend(button);
    });
    // One listener for every share button, so copies of a card (popped up over the page) work too
    document.addEventListener('click', async (ev) => {
        const button = ev.target.closest('.share-link');
        if (!button) return;
        ev.stopPropagation();
        await copy(location.origin + location.pathname + '#' + button.dataset.anchor);
        button.textContent = '✓ copied';
        button.classList.add('copied');
        setTimeout(() => { button.textContent = '🔗'; button.classList.remove('copied'); }, 1600);
    });
    const wanted = decodeURIComponent(location.hash.slice(1));
    const target = wanted && document.querySelector(`[data-share="${CSS.escape(wanted)}"]`);
    if (target) addEventListener('load', () => setTimeout(() => target.scrollIntoView({block: 'start'}), 300));
});

// Hover cards in place of tooltips, everywhere (Oct 28, the person: "we should completely abandon tooltips as a
// feature. Everywhere we have a tooltip we should have an actual pop up"; "mouse over card pop up", "click to keep
// open"). Whatever has a title (an HTML element, or an SVG mark with a <title> inside) shows its text in a card beside
// it on hover or keyboard focus; a click keeps the card open (a link or button still does its own thing on click), and
// ✕, Escape or a click elsewhere closes it. Pages with richer cards register them: hoverCard.register(selector, build),
// where build(element) returns the card's content (a node or an HTML string). Cards sit in window coordinates, inside
// the full-screen overlay when the mark is in one (index.js's chart-full), so they work there too.
// The title moves to data-tip (and to aria-label where the element has no text of its own), so the browser never shows
// its own tooltip on top. data-tip-head gives the card a heading; data-tip-href a link at its foot.
window.hoverCard = (() => {
    const registry = [];
    let card = null, anchor = null, pinned = false, showTimer = null, hideTimer = null;
    const SKIP = 'iframe, frame, object, embed, link, meta, head, html, title, input, select, textarea';

    function adopt(el) {
        // An element's title (or its SVG <title> child) becomes data-tip: no browser tooltip, the text kept
        if (!el || el.dataset?.tip !== undefined) return el;
        let text = null;
        if (el instanceof SVGElement) {
            const t = [...el.children].find((c) => c.tagName.toLowerCase() === 'title');
            if (t) { text = t.textContent.trim(); t.remove(); }
        } else if (el.hasAttribute('title') && !el.matches(SKIP)) {
            text = el.getAttribute('title');
            el.removeAttribute('title');
        }
        if (!text) return null;
        el.dataset.tip = text;
        if (!el.getAttribute('aria-label') && !(el.textContent || '').trim()) el.setAttribute('aria-label', text);
        else if (!el.getAttribute('aria-label')) el.setAttribute('aria-description', text);
        return el;
    }

    function sweep(root) {
        root.querySelectorAll('[title]').forEach((el) => { if (!el.matches(SKIP)) adopt(el); });
        root.querySelectorAll('svg title').forEach((t) => { if (t.parentElement && t.parentElement.tagName.toLowerCase() !== 'svg') adopt(t.parentElement); });
    }

    function find(target) {
        // The nearest element with a card: a registered one first, then anything with a tip or a title
        if (!target || !target.closest) return null;
        for (const [sel, build] of registry) {
            const el = target.closest(sel);
            if (el) { adopt(el); return {el, build}; }  // its <title> goes too, or the browser shows it over the card
        }
        let el = target;
        while (el && el !== document.body && el !== document.documentElement) {
            if (el.dataset && el.dataset.tip !== undefined) return {el, build: tipCard};
            if (el.hasAttribute && (el.hasAttribute('title') || (el instanceof SVGElement && [...el.children].some((c) => c.tagName.toLowerCase() === 'title')))) {
                if (adopt(el)) return {el, build: tipCard};
            }
            el = el.parentElement;
        }
        return null;
    }

    function tipCard(el) {
        // The card for a plain tip: "Name, when: text" reads as a heading and a line; a heading of its own wins
        const frag = document.createDocumentFragment();
        let head = el.dataset.tipHead || '', body = el.dataset.tip || '';
        const split = !head && body.match(/^([^:]{2,90}?):\s+([\s\S]{3,})$/);
        if (split && !/^https?$/i.test(split[1])) { head = split[1]; body = split[2]; }
        if (head) {
            const h = document.createElement('div');
            h.className = 'hover-card-head';
            h.textContent = head;
            frag.append(h);
        }
        body.split('\n').forEach((line) => {
            if (!line.trim()) return;
            const p = document.createElement('div');
            p.className = 'hover-card-line';
            p.textContent = line;
            frag.append(p);
        });
        if (el.dataset.tipHref) {
            const a = document.createElement('a');
            a.className = 'hover-card-more';
            a.href = el.dataset.tipHref;
            a.textContent = el.dataset.tipLink || 'open →';
            frag.append(a);
        }
        return frag;
    }

    function ensure(host) {
        if (!card) {
            card = document.createElement('div');
            card.className = 'hover-card';
            card.hidden = true;
            card.addEventListener('pointerenter', () => clearTimeout(hideTimer));
            card.addEventListener('pointerleave', (ev) => { if (!pinned && ev.pointerType !== 'touch') later(); });
        }
        if (card.parentNode !== host) host.appendChild(card);
        return card;
    }

    function place() {
        // Beside what you point at (right, else left), or under or over it on a phone; the card is a speech bubble
        // (Oct 29, the person: "Can we make our mouseover chips speech bubbles? It's kind of our thing"), so its tail
        // goes on the side facing the mark, as near the mark's middle as the card's corners allow
        if (!card || card.hidden || !anchor || !anchor.isConnected) return;
        const r = anchor.getBoundingClientRect(), gap = 18, pad = 8;
        card.style.left = '0px'; card.style.top = '0px';
        const w = card.offsetWidth, h = card.offsetHeight;
        const vw = document.documentElement.clientWidth, vh = innerHeight;
        const clamp = (v, lo, hi) => Math.min(Math.max(lo, v), Math.max(lo, hi));
        let x, y, side;
        if (r.right + gap + w <= vw - pad) { x = r.right + gap; y = r.top + r.height / 2 - h / 2; side = 'right'; }
        else if (r.left - gap - w >= pad) { x = r.left - gap - w; y = r.top + r.height / 2 - h / 2; side = 'left'; }
        else {  // no room either side (a phone): under it, or over it
            x = clamp(r.left + r.width / 2 - w / 2, pad, vw - w - pad);
            side = r.bottom + gap + h <= vh - pad ? 'below' : 'above';
            y = side === 'below' ? r.bottom + gap : r.top - gap - h;
        }
        x = clamp(x, pad, vw - w - pad);
        y = clamp(y, pad, vh - h - pad);
        card.style.left = `${x}px`;
        card.style.top = `${y}px`;
        const across = side === 'right' || side === 'left';
        const tail = across ? clamp(r.top + r.height / 2 - y, 16, h - 16) : clamp(r.left + r.width / 2 - x, 22, w - 16);
        card.dataset.side = side;
        card.style.setProperty('--tail', `${Math.round(tail)}px`);
    }

    function show(el, build, pin) {
        clearTimeout(showTimer); clearTimeout(hideTimer);
        if (anchor && anchor !== el) anchor.classList.remove('hover-card-on');
        const host = el.closest('.chart-full') || document.body;
        ensure(host);
        if (anchor !== el || card.hidden) {
            const content = build(el);
            if (content == null) return;
            if (typeof content === 'string') card.innerHTML = content; else card.replaceChildren(content);
        }
        anchor = el;
        pinned = Boolean(pin);
        card.classList.toggle('pinned', pinned);
        card.setAttribute('role', pinned ? 'dialog' : 'tooltip');
        card.querySelector(':scope > .hover-card-close')?.remove();
        if (pinned) {
            const x = document.createElement('button');
            x.type = 'button';
            x.className = 'hover-card-close';
            x.setAttribute('aria-label', 'Close');
            x.textContent = '✕';
            x.addEventListener('click', (ev) => { ev.stopPropagation(); hide(true); });
            card.prepend(x);
        }
        // A tint where an element asks for one (lean colors on chips)
        card.style.setProperty('--bubble', el.dataset.tooltipColor || '');  // the tail takes the tint too
        card.style.color = el.dataset.tooltipInk || '';
        el.classList.add('hover-card-on');
        card.hidden = false;
        place();
    }

    function hide(force) {
        clearTimeout(showTimer); clearTimeout(hideTimer);
        if (pinned && !force) return;
        pinned = false;
        if (card) { card.hidden = true; card.classList.remove('pinned'); }
        if (anchor) anchor.classList.remove('hover-card-on');
        anchor = null;
    }

    function later() { clearTimeout(hideTimer); hideTimer = setTimeout(() => hide(false), 250); }

    const acts = (el) => el.closest('a[href], button, summary, label');  // a click that already does something

    document.addEventListener('pointerover', (ev) => {
        if (ev.pointerType === 'touch') return;
        if (card && card.contains(ev.target)) { clearTimeout(hideTimer); return; }
        const hit = find(ev.target);
        if (!hit) return;
        if (pinned) return;  // a kept card stays until it's closed or another is clicked
        clearTimeout(hideTimer); clearTimeout(showTimer);
        if (hit.el === anchor && card && !card.hidden) return;
        showTimer = setTimeout(() => show(hit.el, hit.build, false), anchor ? 0 : 90);
    });
    document.addEventListener('pointerout', (ev) => {
        if (ev.pointerType === 'touch' || pinned) return;
        clearTimeout(showTimer);
        const into = ev.relatedTarget;
        if (anchor && into && (anchor.contains(into) || (card && card.contains(into)))) return;
        if (anchor) later();
    });
    document.addEventListener('click', (ev) => {
        if (card && card.contains(ev.target)) return;
        const hit = find(ev.target);
        if (!hit) { if (card && !card.hidden) hide(true); return; }
        const registered = registry.some(([sel]) => hit.el.matches(sel));
        const link = acts(ev.target);
        if (link && !registered && !(link instanceof SVGElement)) { hide(true); return; }  // a link or button: its own click
        if (registered && link) ev.preventDefault();
        if (pinned && anchor === hit.el) { hide(true); return; }
        show(hit.el, hit.build, true);
    });
    document.addEventListener('focusin', (ev) => {
        if (card && card.contains(ev.target)) return;
        const hit = find(ev.target);
        if (hit && !pinned) show(hit.el, hit.build, false);
    });
    document.addEventListener('focusout', (ev) => {
        if (pinned) return;
        const into = ev.relatedTarget;
        if (into && card && card.contains(into)) return;
        if (anchor && anchor.contains(ev.target)) later();
    });
    document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && card && !card.hidden) { hide(true); anchor?.focus?.(); }
        if ((ev.key === 'Enter' || ev.key === ' ') && ev.target instanceof SVGElement) {
            const hit = find(ev.target);
            if (hit) { ev.preventDefault(); show(hit.el, hit.build, true); }
        }
    });
    addEventListener('scroll', place, {passive: true});
    addEventListener('resize', place);
    document.addEventListener('DOMContentLoaded', () => sweep(document));
    if (document.readyState !== 'loading') sweep(document);
    return {
        register(selector, build) { registry.push([selector, build]); },
        show(el, build, pin) { show(el, build || tipCard, pin); },
        hide() { hide(true); },
        sweep,
    };
})();

// Charts open full screen (Oct 28, the person, of a saga's charts on a phone: "these deserve to be fullscreenable").
// A button on each story and saga chart opens it in an overlay over the whole window; on a phone held upright the chart
// is turned on its side to use the long edge. The phone's back button, Escape, the ✕ or a tap outside close it. Phones'
// browsers mostly can't put a page element in true full screen (iPhones only video), so it's an overlay everywhere,
// asked to go full screen where the browser allows.
document.addEventListener('DOMContentLoaded', () => {
    let open = null;
    function close(fromHistory) {
        if (!open) return;
        open.remove();
        open = null;
        document.documentElement.classList.remove('chart-full-on');
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        if (!fromHistory && history.state && history.state.chartFull) history.back();
    }
    function show(svg, label) {
        const overlay = document.createElement('div');
        overlay.className = 'chart-full';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', label || 'Chart, full screen');
        const shut = document.createElement('button');
        shut.type = 'button';
        shut.className = 'chart-full-close';
        shut.setAttribute('aria-label', 'Close');
        shut.textContent = '✕';
        const stage = document.createElement('div');
        stage.className = 'chart-full-stage';
        const copy = svg.cloneNode(true);
        copy.removeAttribute('width');
        copy.removeAttribute('height');
        copy.classList.add('chart-full-svg');
        stage.appendChild(copy);
        overlay.append(stage, shut);
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) close(false); });
        shut.addEventListener('click', () => close(false));
        document.body.appendChild(overlay);
        document.documentElement.classList.add('chart-full-on');
        open = overlay;
        history.pushState({chartFull: true}, '');
        if (overlay.requestFullscreen) overlay.requestFullscreen().catch(() => {});
        shut.focus();
    }
    window.addEventListener('popstate', () => close(true));
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') close(false); });
    document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && open) close(false); });
    document.querySelectorAll('svg.story-chart').forEach((svg) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chart-full-open';
        button.textContent = '⛶ full screen';
        const caption = svg.closest('figure')?.querySelector('figcaption')?.textContent.trim();
        button.addEventListener('click', () => show(svg, caption));
        svg.parentNode.insertBefore(button, svg);
    });
});
