"""A tripwire for class-name clashes. Twice on Oct 6 a new rule reused a class another component already had (.tv-bar on
the story page stretched bars across its text; .wb-bar in the workbench's stats squeezed its top bar into a column).
Each class defined as a base rule (`.name { … }`) in more than one place is listed here; a new one fails, so whoever
adds it checks first whether the name already belongs to something else. If the repeat is meant (a later partial
adjusting an earlier component), add it to the list with a word on why."""
import collections
import glob
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), '..')

# Repeats that are meant: later partials adjusting the component, or a page's own variant (as of Oct 6)
KNOWN = {
    'workbench': {'.wb-pname', '.wb-tree-tools'},
    'site': {'.cloud-detail', '.cloud-word', '.court-meta', '.court-story', '.edit-chip', '.emotion-tile',
             '.emotion-tile-emoji', '.emotion-tile-label', '.emotion-tile-share', '.emotion-tiles', '.flow-when',
             '.metric-name', '.metric-value', '.newsday-sticker', '.outlet-card', '.outlet-rewrite', '.quote-chip',
             '.show-chip', '.story', '.story-chart', '.story-flow', '.story-quotes', '.story-sort', '.story-wording',
             '.storylink', '.table-intro', '.term', '.top-facts', '.top-more', '.trending', '.trending-row',
             '.wording-chip'},
}


def base_rules(text: str) -> list[str]:
    """Selectors that are a single class, in rules outside @media"""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}', '', text)  # a media query adjusts, it doesn't define
    return [sel.strip() for m in re.finditer(r'([^{}]+)\{[^{}]*\}', text)
            for sel in m.group(1).split(',') if re.fullmatch(r'\s*\.[\w-]+\s*', sel)]


def repeats(files: list[str]) -> set[str]:
    seen = collections.Counter(sel for f in files for sel in base_rules(open(f, encoding='utf-8').read()))
    return {sel for sel, n in seen.items() if n > 1}


def test_no_new_class_is_defined_twice():
    groups = {'workbench': [os.path.join(ROOT, 'scripts/checker/static/workbench.css')],
              'site': sorted(glob.glob(os.path.join(ROOT, 'app/site/styles/*.css')))}
    for name, files in groups.items():
        new = repeats(files) - KNOWN[name]
        assert not new, (f'{name}: {sorted(new)} defined more than once: does the name already belong to another '
                         f'component? (grep the styles) If the repeat is meant, add it to KNOWN in this test')
