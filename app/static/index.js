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

function determineSmiley(value) {
    if (value > 0.1) {
        return '😊';
    } else if (value < -0.1) {
        return '😭';
    }
    return '';
}

function recenter(value) {
    return (value + 0.2) / (2 * 0.2);
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function getColorForValue(value) {
    if (value === 'N/A')
        return 'white';
    if (value == null)
        return '#f9fafb';

    let a = recenter(value);
    let b = 120 * a;
    let c = clamp(b, 0, 120);
    console.log(c);

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