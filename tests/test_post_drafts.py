"""The Bluesky drafts' pure parts: whole lines under the limit, wordings alike but for quotes counted once, marks."""
import pytest

from app import post_drafts as p


def test_fits_keeps_whole_lines_and_counts_the_rest():
    lines = [f'• {"word " * 20}{i}' for i in range(10)]
    text = p.fits('Head:', lines)
    assert len(text) <= p.LIMIT
    shown = [x for x in text.split('\n') if x.startswith('•')]
    assert all(x in lines for x in shown)  # never a line cut short
    assert text.endswith(f'+{10 - len(shown)} more')


def test_fits_everything_when_it_fits():
    assert p.fits('Head:', ['a', 'b'], '\n(tail)') == 'Head:\na\nb\n(tail)'


def test_same_words_sets_quotes_and_case_aside():
    assert p.same_words('I’m in My 30s. “Old” People') == p.same_words("I'm in my 30s. \"Old\" people")
    assert p.same_words('One wording') != p.same_words('Another wording')


def test_marks(tmp_path):
    file = str(tmp_path / 'drafts.json')
    p.write_json(file, {'drafts': [{'key': 'rewrite:x', 'format': 'rewrite', 'text': 't', 'mark': None}]})
    state = p.mark('rewrite:x', 'down', '  too   dull ', file=file)
    assert state['drafts'][0]['mark'] == 'down' and state['drafts'][0]['note'] == 'too dull'
    assert next(f for f in state['formats'] if f['id'] == 'rewrite')['down'] == 1
    with pytest.raises(ValueError):
        p.mark('rewrite:x', 'maybe', file=file)
    with pytest.raises(ValueError):
        p.mark('nothing', 'up', file=file)


def test_front_page_theme_and_its_biggest_hour_kept(tmp_path, monkeypatch):
    from datetime import datetime as dt
    monkeypatch.setattr(p.Config, 'data', str(tmp_path))
    titles = ['Shooting after football game leaves 1 dead', 'Shootings in Dallas leave 4 dead',
              'Pregnant woman killed in Halloween store shooting', 'Gunman opened fire at a mall', 'Senate race tightens',
              'Israel under fire over strikes']
    p.write_json(str(tmp_path / 'top_stories.json'), {'stories': [{'title': t} for t in titles]})
    found = {d['key'].split('|')[1]: d for d in p.front_page_themes(dt(2026, 11, 1, 21))}
    assert set(found) == {'shootings'}  # gunfire and "under fire" are not fires
    assert found['shootings']['text'].startswith('🚨 4 of the top 6 stories right now are about shootings:')
    file = str(tmp_path / 'drafts.json')
    monkeypatch.setattr(p, 'MAKERS', [p.front_page_themes])
    p.make(dt(2026, 11, 1, 21), file=file)
    p.write_json(str(tmp_path / 'top_stories.json'), {'stories': [{'title': t} for t in titles[1:4]]})
    p.make(dt(2026, 11, 1, 22), file=file)
    kept = p.read_json(file)['drafts'][0]
    assert kept['peak'] == 4 and kept['seen'] == '2026-11-01T22:00'
