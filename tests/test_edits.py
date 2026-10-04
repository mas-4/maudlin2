"""Headline edits: word extraction, kicker stripping, overlap, minor-change detection and the diff markup."""
import pytest

from app.analysis.edits import LIVE, _core, _words, diff_html, is_minor, overlap


@pytest.mark.parametrize('text, expected', [
    ('Storm Hits Coast', ['storm', 'hits', 'coast']),
    ('It’s $5 and 10% off, OK?', ["it's", '$5', 'and', '10%', 'off', 'ok']),  # curly apostrophe normalized
    ('', []),
    ('— … !!', []),
])
def test_words(text, expected):
    assert _words(text) == expected


@pytest.mark.parametrize('text', [
    'WEEKEND: Storm hits coast',
    'HIJACK PROBE  Storm hits coast',  # caps tag set off by a double space
    'Exclusive — Storm hits coast',
    'Video: Storm hits coast',
    'watch | Storm hits coast',
    'Breaking - Live: Storm hits coast',  # stacked labels
    'UPDATED: Storm hits coast',
    '…Storm hits coast...',
    'Storm hits coast…',
    '  Storm, hits; coast!  ',
])
def test_core_strips_kickers_case_and_punctuation(text):
    assert _core(text) == ['storm', 'hits', 'coast']


def test_core_keeps_leading_capitalized_word_without_separator():
    assert _core('NASA launches rocket') == ['nasa', 'launches', 'rocket']


def test_core_keeps_label_words_mid_headline():
    assert _core('Senators watch: video of vote') == ['senators', 'watch', 'video', 'of', 'vote']


def test_overlap():
    assert overlap('a b c', 'a b d') == pytest.approx(2 / 4)
    assert overlap('Storm hits coast', 'storm HITS coast!') == 1.0
    assert overlap('WEEKEND: storm hits', 'storm hits') == 1.0
    assert overlap('Senate passes bill', 'Hurricane nears Florida') == 0.0


def test_overlap_empty_is_zero_not_error():
    assert overlap('', '') == 0.0
    assert overlap('...', 'Storm') == 0.0


def test_overlap_is_symmetric():
    a, b = 'Senate passes budget bill', 'House rejects Senate budget'
    assert overlap(a, b) == overlap(b, a)


@pytest.mark.parametrize('before, after', [
    ('Storm hits coast', 'storm hits coast'),  # capitalization
    ('Storm hits coast', 'Storm hits coast!'),  # punctuation
    ('Storm hits coast', 'Storm, hits — coast'),
    ('Storm hits coast', 'WEEKEND: Storm hits coast'),  # kicker added
    ('Exclusive: Storm hits coast', 'Storm hits coast'),  # label dropped
    ('Storm hits coast', 'Storm hits coast, killing 12'),  # one contains the other
    ('Storm hits coast as residents flee', 'Storm hits coast…'),  # truncation
    ('Biden’s plan stalls', "Biden's plan stalls"),  # apostrophe style
])
def test_is_minor(before, after):
    assert is_minor(before, after)
    assert is_minor(after, before)


@pytest.mark.parametrize('before, after', [
    ('Storm hits coast', 'Storm batters coast'),
    ('Storm hits coast', 'Storm hits the coast'),  # an inserted word breaks containment
    ('Senate passes bill', 'Senate rejects bill'),
    ('Senator resigns after scandal', 'Senator refuses to resign despite scandal'),
])
def test_is_not_minor(before, after):
    assert not is_minor(before, after)


def test_is_minor_containment_is_by_characters_not_words():
    # Documents current behavior: containment is checked on the joined strings, so a word that grows counts
    assert is_minor('Senate passes bill', 'Senate passes billionaire tax')


def test_diff_html_marks_changed_words():
    old, new = diff_html('Storm hits coast', 'Storm batters coast')
    assert old == 'Storm <del>hits</del> coast'
    assert new == 'Storm <ins>batters</ins> coast'


def test_diff_html_case_only_change_is_unmarked():
    old, new = diff_html('Storm hits coast', 'storm hits coast')
    assert '<del>' not in old and '<ins>' not in new
    assert old == 'Storm hits coast' and new == 'storm hits coast'  # each side keeps its own case


def test_diff_html_insertion_and_deletion():
    assert diff_html('A B', 'A B C') == ('A B', 'A B <ins>C</ins>')
    assert diff_html('A B C', 'A C') == ('A <del>B</del> C', 'A C')


def test_diff_html_groups_adjacent_changes():
    old, new = diff_html('Fed holds rates steady today', 'Fed cuts rates sharply today')
    assert old == 'Fed <del>holds</del> rates <del>steady</del> today'
    assert new == 'Fed <ins>cuts</ins> rates <ins>sharply</ins> today'
    old, new = diff_html('one two three', 'one four five three')
    assert old == 'one <del>two</del> three'
    assert new == 'one <ins>four five</ins> three'


def test_diff_html_escapes_html():
    old, new = diff_html('Tom & Jerry <b>"win"</b>', 'Tom & Jerry <b>lose</b>')
    assert '<b>' not in old and '<b>' not in new
    assert old.startswith('Tom &amp; Jerry')
    assert '<del>&lt;b&gt;&quot;win&quot;&lt;/b&gt;</del>' in old
    assert '<ins>&lt;b&gt;lose&lt;/b&gt;</ins>' in new


def test_diff_html_collapses_whitespace():
    assert diff_html('Storm   hits\ncoast', 'Storm hits coast') == ('Storm hits coast', 'Storm hits coast')


def test_diff_html_full_rewrite():
    old, new = diff_html('Senate passes bill', 'Hurricane nears Florida')
    assert old == '<del>Senate passes bill</del>'
    assert new == '<ins>Hurricane nears Florida</ins>'


@pytest.mark.parametrize('title, live', [
    ('LIVE: Storm hits coast', True),
    ('Election live updates: polls close', True),
    ('Ukraine war live blog', True),
    ('Budget vote – as it happened', True),
    ('Olivia lives in Paris', False),
    ('Delivery firm expands', False),
])
def test_live_pattern(title, live):
    assert bool(LIVE.search(title)) is live


@pytest.mark.xfail(reason="LIVE is compiled with re.IGNORECASE, so the all-caps \\bLIVE\\b branch matches any word "
                          "'live' and ordinary headlines ('Live music...', 'Where to live') are skipped as live blogs")
@pytest.mark.parametrize('title', ['Live music returns to Austin', 'The best cities to live in'])
def test_live_pattern_ignores_plain_word_live(title):
    assert not LIVE.search(title)
