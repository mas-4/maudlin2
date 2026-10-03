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
