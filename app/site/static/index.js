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
function packColumns(box, cards, minWidth) {
    let current = cards, count = 0;
    function layout(next, force) {
        if (next) current = next;
        const n = Math.max(1, Math.floor(box.clientWidth / minWidth));
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
