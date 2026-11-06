"""The news over time page (app/analysis/over_time.py, app/analysis/galaxy.py, app/site/page_over_time.py): its
series from plain rows, the galaxy's layout kept and added to, and the page's markup"""
import json
import re
import zlib
from datetime import date, datetime as dt

import numpy as np
import pytest
from bs4 import BeautifulSoup

from app.analysis import galaxy, over_time as ot
from app.site import page_over_time as pot


DAYS = ot.days_between('2026-10-02', '2026-10-06')


def test_days_are_eastern():
    assert ot.local_day(dt(2026, 10, 3, 3, 30)) == '2026-10-02'  # 11:30 PM ET the day before
    assert ot.local_day(dt(2026, 10, 3, 4, 30)) == '2026-10-03'
    assert ot.days_between('2026-10-30', '2026-11-02') == ['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02']


def test_emotion_days_split_each_vote_and_leave_out_thin_days(monkeypatch):
    monkeypatch.setattr(ot, 'MIN_DAY_HEADLINES', 2)
    rows = [('2026-10-02', 'fear')] * 3 + [('2026-10-02', 'anger,fear')] + [('2026-10-03', 'joy')] + \
           [('2026-10-09', 'fear')] * 5  # outside the days: not counted
    out = ot.emotion_days(rows, DAYS)
    assert out['counts'] == [4, 1, 0, 0, 0]
    assert out['shares']['fear'][0] == pytest.approx((3 + 1 / 3) / 4, abs=1e-4)
    assert out['shares']['anger'][0] == pytest.approx((2 / 3) / 4, abs=1e-4)
    assert out['shares']['joy'][1] is None  # one headline: too thin a day to draw
    assert out['feelings'][-1] == 'neutral'


def test_emotion_spikes_pick_the_days_furthest_above_usual(monkeypatch):
    monkeypatch.setattr(ot, 'MIN_DAY_HEADLINES', 1)
    series = {'counts': [10] * 5, 'shares': {e: [0.1] * 5 for e in ot.FEELINGS}}
    series['shares']['fear'] = [0.1, 0.1, 0.3, 0.1, 0.12]
    series['shares']['joy'] = [0.05, 0.05, 0.2, 0.05, 0.05]  # higher above usual, the same day as fear's
    series['shares']['anger'] = [0.1, 0.1, 0.1, 0.1, 0.15]
    tops = {('2026-10-04', 'joy'): {'story': 7, 'label': 'A happy story', 'headlines': 5}}
    out = ot.emotion_spikes(series, DAYS, tops, n=3)
    # fear's Oct 4 is joy's day, which ran further above its usual; anger's Oct 6 beats fear's next best there
    assert [(s['day'], s['feeling']) for s in out] == [('2026-10-04', 'joy'), ('2026-10-06', 'anger')]
    assert out[0]['label'] == 'A happy story' and out[0]['lift'] == 4.0
    assert 'label' not in out[1]  # no story led by anger that day


def test_top_stories_count_each_days_leading_feeling():
    rows = [('d1', 'fear', 1, 'A'), ('d1', 'fear', 1, 'A'), ('d1', 'fear', 2, 'B'), ('d1', 'joy', 2, 'B'),
            ('d1', 'fear', None, None)]
    out = ot.top_stories(rows)
    assert out[('d1', 'fear')] == {'story': 1, 'label': 'A', 'headlines': 2}
    assert out[('d1', 'joy')]['story'] == 2


def test_motif_tides_rank_by_the_busiest_week():
    entries = [{'id': 'M1', 'name': 'Steady', 'genre': 'Plots', 'claims': [{'date': d} for d in DAYS]},
               {'id': 'M2', 'name': 'Burst', 'genre': 'Theories', 'claims': [{'date': '2026-10-04T10:00'}] * 7},
               {'id': 'M3', 'name': 'Old', 'genre': '', 'claims': [{'date': '2026-07-01'}]}]
    out = ot.motif_tides(entries, DAYS)
    assert [m['id'] for m in out['motifs']] == ['M2', 'M1']  # an old claim alone isn't in the record's days
    assert out['motifs'][0]['peak'] == {'day': '2026-10-04', 'n': 7}
    assert out['all'] == [1, 1, 8, 1, 1]


def test_best_week():
    assert ot.best_week([1, 0, 0, 0, 0, 0, 0, 5, 5]) == 10
    assert ot.best_week([2, 3]) == 5
    assert ot.best_week([]) == 0


def test_saga_lines_keep_the_biggest():
    rows = [(1, '2026-10-02')] * 3 + [(1, '2026-10-05')] + [(2, '2026-10-03')] * 9 + [(3, '2026-10-04')]
    out = ot.saga_lines(rows, {1: 'One', 2: 'Two'}, DAYS, top=2)  # 3 has no page
    assert [s['name'] for s in out] == ['One', 'Two']  # the earliest first
    assert out[0]['first'] == '2026-10-02' and out[0]['last'] == '2026-10-05' and out[0]['total'] == 4
    assert out[1]['peak'] == {'day': '2026-10-03', 'n': 9}


def test_newsiness_series_shares_story_labels():
    pts = [{'at': '2026-10-10T01:00:00', 'score': 0.3, 'story': 1, 'label': 'A', 'outlets': 30, 'active': 90,
            'made': 'reconstructed'},
           {'at': '2026-10-10T02:00:00', 'score': 0.5, 'story': 1, 'label': 'A', 'outlets': 45, 'active': 90,
            'made': 'recorded'}]
    out = ot.newsiness_series(pts, [pts[1]], lambda p: f"story-{p['story']}.html")
    assert out['stories'] == ['A']
    assert out['points'][1] == ['2026-10-10T02:00:00', 0.5, 1, 0, 45, 90]
    assert out['spikes'][0]['href'] == 'story-1.html'


def test_cluster_labels_only_for_groups_that_sit_together():
    rng = np.random.default_rng(0)
    xy = np.vstack([0.2 + rng.normal(0, 0.005, (150, 2)), rng.uniform(0, 1, (150, 2))])
    day = np.arange(300) % 5
    groups = {'tight': {'name': 'Tight', 'href': 'saga-1.html', 'rows': list(range(150))},
              'loose': {'name': 'Loose', 'href': None, 'rows': list(range(150, 300))},
              'small': {'name': 'Small', 'rows': [0, 1]}}
    (label,) = ot.cluster_labels(xy, groups, day)
    assert label['name'] == 'Tight' and label['n'] == 150 and label['days'] == [0, 4]
    assert abs(label['x'] - 0.2) < 0.01


# ---- the galaxy

def fake_embed(texts):
    """Bag of hashed words: headlines sharing words sit together"""
    out = np.zeros((len(texts), 64))
    for i, t in enumerate(texts):
        for w in re.findall(r'\w+', t.lower()):
            out[i, zlib.crc32(w.encode()) % 64] += 1
    out[:, 0] += 1e-3
    return out


@pytest.fixture
def sky(tmp_path, monkeypatch):
    monkeypatch.setattr(galaxy, 'embed', fake_embed)
    monkeypatch.setattr(galaxy, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(galaxy, 'LAYOUT_FILE', str(tmp_path / 'layout.npz'))
    monkeypatch.setattr(galaxy, 'LANDMARKS', 80)
    monkeypatch.setattr(galaxy, 'TOPICS', 3)
    words = ['senate vote budget', 'storm flood rain', 'game win team', 'market stock price']
    titles = [f'{words[i % 4]} {i % 7} news' for i in range(200)]
    return np.arange(1000, 1200), titles


def test_galaxy_lays_out_once_then_places_only_new_headlines(sky, monkeypatch):
    ids, titles = sky
    first = galaxy.today(ids[:150], titles[:150])
    assert first['xy'].shape == (150, 2) and first['xy'].min() >= 0 and first['xy'].max() <= 1
    assert len(first['names']) == 3 and sum(bool(n) for n in first['names']) >= 2  # a mixed topic may go unnamed
    assert set(first['topic']) <= {0, 1, 2}

    def no_relayout(*a, **k):
        raise AssertionError('laid out again')
    monkeypatch.setattr(galaxy, 'fresh', no_relayout)
    second = galaxy.today(ids, titles)
    assert second['placed'] == 50
    np.testing.assert_allclose(second['xy'][:150], first['xy'])  # the kept places stay put
    # a new headline sits near the old ones that say the same thing
    same = [i for i in range(150) if titles[i] == titles[160]]
    assert np.linalg.norm(second['xy'][160] - second['xy'][same].mean(0)) < 0.25


def test_galaxy_is_laid_out_again_after_a_week(sky):
    ids, titles = sky
    galaxy.today(ids, titles)
    kept = galaxy.load()
    assert not galaxy.stale(kept, date.fromisoformat(kept['made']))
    assert galaxy.stale(kept, date.fromordinal(date.fromisoformat(kept['made']).toordinal() + galaxy.RELAYOUT_DAYS))
    assert galaxy.stale({**kept, 'version': galaxy.VERSION + 1})


def test_topic_names_skip_words_every_topic_uses():
    titles = ['says senate vote'] * 30 + ['says storm flood'] * 30
    names = galaxy.topic_names(titles, np.array([0] * 30 + [1] * 30), 2, words=2)
    assert 'says' not in ' '.join(names)
    assert 'senate' in names[0] and 'storm' in names[1]


def test_galaxy_files_hold_every_headline(sky, monkeypatch, tmp_path):
    ids, titles = sky
    monkeypatch.setattr(pot.Config, 'build', str(tmp_path / 'build'))
    monkeypatch.setattr(pot, 'CHUNK', 64)
    rows = [(int(i), t, None, 'AP', 0.9, 'fear', 5 if k < 130 else None, 'A story', 9 if k < 130 else None)
            for k, (i, t) in enumerate(zip(ids, titles))]
    days = ['2026-10-02', '2026-10-03']
    local = ['2026-10-03'] * len(rows)
    out = pot.write_galaxy(rows, days, local, {5}, {9: 'A saga'})
    blob = (tmp_path / 'build' / 'galaxy' / 'points.bin').read_bytes()
    n = len(rows)
    assert out['n'] == n and len(blob) == 7 * n == out['bytes']
    assert np.frombuffer(blob, '<u2', n, 4 * n).tolist() == [1] * n  # each headline's day
    chunk = json.loads((tmp_path / 'build' / 'galaxy' / 't-3.json').read_text())
    assert len(chunk) == n - 3 * 64
    assert chunk[0][:3] == [titles[192], 'AP', 'Oct 3']
    first = json.loads((tmp_path / 'build' / 'galaxy' / 't-0.json').read_text())
    assert first[0][3:] == ['A story', 'story-5.html']
    from PIL import Image
    with Image.open(tmp_path / 'build' / 'galaxy' / pot.PREVIEW) as im:  # the picture the charts page links with
        assert im.size == (1200, 630)
        assert im.getpixel((0, 0)) == pot.SKY
    assert [t['ink'] for t in out['topics']] == pot.TOPIC_INK[:3]


def test_page_renders(monkeypatch, tmp_path):
    monkeypatch.setattr(pot.Config, 'build', str(tmp_path))
    page = pot.OverTimePage()
    page.context.update({'data': {'days': DAYS, 'today': DAYS[-1], 'galaxy': None, 'newsiness': None, 'tides': None,
                                  'emotions': None, 'sagas': None, 'x': '</script><b>'},
                         'headlines': 12345, 'start': 'Oct 2', 'galaxy': None, 'tides': None})
    page.template.write(page.context)
    html = (tmp_path / 'over-time.html').read_text()
    soup = BeautifulSoup(html, 'html.parser')
    assert soup.select_one('h2.story-page-title').get_text() == 'The news over time'
    assert {f['id'] for f in soup.select('.ot-chart')} == {'ot-newsiness-chart', 'ot-tides-chart', 'ot-feelings-chart',
                                                           'ot-sagas-chart'}
    assert '</script><b>' not in html  # the data can't close its own script
    assert json.loads(soup.select_one('#ot-data').string)['x'] == '</script><b>'
    assert soup.select_one('script[src^="over_time.js"]') is not None
    assert '12,345' in html


def test_galaxy_page_is_the_whole_page(tmp_path, monkeypatch):
    """The galaxy's own page (Nov 5): no site menu or footer, a big way back, and its data for galaxy.js"""
    monkeypatch.setattr(pot.Config, 'build', str(tmp_path))
    G = {'n': 321652, 'chunk': 1000, 'stamp': 's', 'made': '2026-11-05', 'labels': [], 'topics': [], 'bytes': 7}
    pot.TemplateHandler('galaxy.html').write({'data': {'days': DAYS, 'galaxy': G}, 'galaxy': G, 'start': 'Oct 2',
                                              'preview': 'galaxy/preview.png'})
    soup = BeautifulSoup((tmp_path / 'galaxy.html').read_text(), 'html.parser')
    assert soup.select_one('a#gx-back')['href'] == 'over-time.html'
    assert soup.select_one('nav') is None and soup.select_one('footer') is None
    assert soup.select_one('link[href^="./style.css"]') is None  # its own stylesheet only
    assert json.loads(soup.select_one('#ot-data').string)['galaxy']['n'] == 321652
    assert soup.select_one('script[src^="galaxy.js"]') is not None
    assert '321,652 headlines' in soup.get_text()
    assert soup.select_one('meta[property="og:image"]')['content'].endswith('/galaxy/preview.png')
