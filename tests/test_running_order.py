from datetime import datetime

from app.analysis import llm, running_order as ro


def test_each_newscast_is_split_once_and_matched_to_that_hours_front_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(ro, 'RUNNING', str(tmp_path / 'running.json'))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    cast = {'source': 'nprnewsnow', 'title': '2pm ET', 'url': 'npr/1', 'published': datetime(2026, 10, 5, 18, 9),
            'text': 'This is NPR News. ' * 20 + 'The investigation into the attack. The co-pilot said. Member station WSKG '
                    'reports. And X. The same story. Mint Mobile here.'}
    short = dict(cast, url='npr/2', text='too short')
    monkeypatch.setattr(ro, 'newscasts', lambda: [cast, short])
    front = [{'id': 26, 'label': 'Trump rallies', 'outlets': 40}, {'id': 70, 'label': 'Dubai flight attack', 'outlets': 30}]
    asked = []
    monkeypatch.setattr(ro, 'stories_at', lambda when: asked.append(when) or front)
    prompts = []

    def complete(prompt, schema, max_tokens, model):
        prompts.append(prompt)
        return {'stories': [{'kind': 'news', 'title': ' Co-pilot  meant to crash ', 'first_words': 'The investigation', 'front': 2},
                            {'kind': 'news', 'title': 'Co-pilot again', 'first_words': 'The co-pilot said', 'front': 2},
                            {'kind': 'news', 'title': 'Cornell building vandalized', 'first_words': 'Member station', 'front': 0},
                            {'kind': 'news', 'title': 'Made up', 'first_words': 'Not in the newscast', 'front': 1},
                            {'kind': 'news', 'title': 'Made up too', 'first_words': 'Member station WSKG', 'front': 1},
                            {'kind': 'news', 'title': 'Out of range', 'first_words': 'And X', 'front': 9},
                            {'kind': 'news', 'title': '', 'first_words': 'The same story', 'front': 1},
                            {'kind': 'ad or promo', 'title': 'Mint Mobile offer', 'first_words': 'Mint Mobile here', 'front': 0}]}
    monkeypatch.setattr(llm, 'complete_json', complete)
    store = ro.read()
    assert list(store) == ['npr/1'] and asked == [cast['published']]
    assert '1. Trump rallies\n2. Dubai flight attack' in prompts[0]
    first, second, third = store['npr/1']['items']
    assert first == {'title': 'Co-pilot meant to crash', 'story': 70, 'story_label': 'Dubai flight attack',
                     'front_rank': 2, 'outlets': 30}
    assert second == {'title': 'Cornell building vandalized'} and third == {'title': 'Out of range'}
    assert store['npr/1']['published'] == '2026-10-05T18:09' and store['npr/1']['show'] == 'NPR News Now'
    ro.read()
    assert len(prompts) == 1  # read once per newscast


def test_abc_newscasts_lose_their_ad_wrapper():
    text = ("From the studio that brought you WandaVision. Streaming October 14th. ABC News. I'm Mike Dubuski. "
            "Measles cases top 1,000. " * 3 + "This is ABC News. Hey, Ryan Reynolds here from Mint Mobile.")
    out = ro.newscast_only('abcupdate', text)
    assert out.startswith("ABC News. I'm Mike") and out.rstrip().endswith('top 1,000.')
    starts_mid_story = 'Today he heads to Nebraska. ' * 5 + 'This is ABC News. Think GLP-1s are too expensive?'
    assert ro.newscast_only('abcupdate', starts_mid_story).startswith('Today he heads')
    assert ro.newscast_only('nprnewsnow', text) == text
