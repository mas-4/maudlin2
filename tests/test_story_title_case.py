"""A story's title takes its words' casing from the outlets' headlines (app/analysis/stories.py restore_case)."""

from app.analysis import stories

DESANTIS = ["DeSantis: GOP Losses Near 'Extinction-Level Event'",
            "'Extinction-level event': DeSantis warns Republican Party faces political catastrophe",
            "DeSantis calls midterm results ‘extinction-level event’ for Republicans"]

HEGSETH = ["Trump weighs making Pete Hegseth the fall guy for Republicans’ crushing Midterm loss: ‘Knives are out’",
           "Trump is asking those in his circle about keeping Hegseth after disastrous midterms: report",
           "Trump weighs making Pete Hegseth the fall guy for Republicans’ crushing midterms loss: ‘Knives are out’"]


def test_a_name_the_model_split_is_joined_back():
    title = stories.restore_case('Ron de santis warns GOP faces extinction-level event', DESANTIS)
    assert title == 'Ron DeSantis warns GOP faces extinction-level event'
    assert stories.restore_case('Ron De-Santis warns GOP', DESANTIS) == 'Ron DeSantis warns GOP'


def test_one_capitalized_common_noun_isnt_a_proper_noun():
    title = stories.restore_case("Trump seeks adviser input on Pete Hegseth's future following midterm losses", HEGSETH)
    assert title == "Trump seeks adviser input on Pete Hegseth's future following midterm losses"


def test_proper_nouns_and_acronyms_still_restored():
    headlines = ['Judge rules against the DOJ in Cornell case', 'Cornell students sue as DOJ probe widens']
    assert stories.restore_case('doj probe of cornell widens in the u.s.', headlines) == \
        'DOJ probe of Cornell widens in the U.S.'


def test_ordinary_word_pairs_are_left_alone():
    assert stories.restore_case('Any one of the bills', ['Anyone can see the Bills lost']) == 'Any one of the bills'


def test_short_words_stay_lowercase_unless_acronyms():
    headlines = ['U.S. strikes Iran As Trump downplays the conflict', 'Iran braces as U.S. strikes; Trump eyes AI']
    assert stories.restore_case('U.S. strikes Iran as Trump eyes ai', headlines) == 'U.S. strikes Iran as Trump eyes AI'


def test_curly_apostrophes_count_as_straight_ones():
    headlines = ['Investors flee as Musk’s companies slide', 'Tesla falls after Musk’s midterm losses']
    assert stories.restore_case("Elon musk's stocks drop", headlines) == "Elon Musk's stocks drop"
