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