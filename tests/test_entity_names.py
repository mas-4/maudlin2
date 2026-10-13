"""app/analysis/entities.py: a title dropped before names merge, and common nouns kept off the names page"""
from app.analysis import entities as en


def test_a_title_goes_only_before_a_full_name():
    assert en.untitled('Rep. Ilhan Omar') == 'Ilhan Omar' and en.untitled('Former President Joe Biden') == 'Joe Biden'
    assert en.untitled('Secretary of State Marco Rubio') == 'Marco Rubio'
    for kept in ('General Motors', 'Justice Department', 'Pope Leo XIV', 'Dr. Oz', 'President Trump'):
        assert en.untitled(kept) == kept


def test_a_common_noun_is_not_a_name_unless_written_as_one():
    assert en.generic('Worker', ['Russian lab worker dies from unknown illness'])
    assert en.generic('Man', ['x']) and en.generic('Police', ['x'])
    assert not en.generic('London', ["trial begins in london"])  # a place, however the label spells it
    assert not en.generic('Apple', ['Investors cheer Apple results'])  # capitalized mid-sentence: the company
    assert not en.generic('Ilhan Omar', ['x'])  # two words: a name
