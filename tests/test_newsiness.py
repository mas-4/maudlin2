"""app/analysis/newsiness.py and its chart (story_charts.newsiness): how newsy each hour was, spikes linked"""
from app.analysis import newsiness as nw
from app.site import story_charts


def point(at, score, story, made='reconstructed', label='A story'):
    return {'at': at, 'score': score, 'share': score, 'outlets': 40, 'active': 80, 'story': story, 'label': label,
            'kind': nw.kind_of(score), 'made': made}


def test_each_story_peaks_once_over_the_big_line():
    pts = [point('2026-10-10T01:00:00', 0.40, 1), point('2026-10-10T02:00:00', 0.46, 1),
           point('2026-10-10T03:00:00', 0.50, 1), point('2026-10-12T13:00:00', 0.48, 2), point('2026-10-12T14:00:00', 0.3, 3)]
    assert [(p['story'], p['score']) for p in nw.spikes(pts)] == [(1, 0.50), (2, 0.48)]


def test_a_build_keeps_its_own_score(monkeypatch, tmp_path):
    monkeypatch.setattr(nw, 'NEWSINESS', str(tmp_path / 'n.json'))
    nw.record({'score': 0.65, 'share': 65, 'outlets': 53, 'active': 81, 'story': 'Omar', 'kind': 'big'}, 358)
    (p,) = nw.load()['recorded']
    assert (p['score'], p['story'], p['share'], p['label']) == (0.65, 358, 0.65, 'Omar')
    nw.record({'share': 10}, None)  # an older build's newsday, without a score: nothing kept
    assert len(nw.load()['recorded']) == 1


def test_the_chart_dashes_what_was_worked_out_and_links_its_spikes():
    pts = [point('2026-10-10T01:00:00', 0.2, 1), point('2026-10-10T02:00:00', 0.5, 1, label='Big one'),
           point('2026-10-10T03:00:00', 0.3, 2, 'recorded'), point('2026-10-10T04:00:00', 0.35, 2, 'recorded')]
    svg = story_charts.newsiness(pts, nw.spikes(pts), lambda p: f"story-{p['story']}.html")
    assert svg.count('<polyline') == 2 and 'stroke-dasharray' in svg.split('<polyline')[1]
    assert '<a href="story-1.html"><text' in svg and 'Big one' in svg and svg.count('class="nw-hit"') == 4
    assert story_charts.newsiness(pts[:1], [], lambda p: None) is None
