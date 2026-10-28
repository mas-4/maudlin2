"""The Replay (app/analysis/replay.py, app/site/page_replay.py): passages heard word for word on several shows, found
by shared 12-word shingles, sorted into clips, campaign ads, sponsor reads and transcription glitches."""
import os
from datetime import datetime as dt, timedelta as td

import numpy as np
from bs4 import BeautifulSoup

from app.analysis import replay
from app.site import page_replay
from app.utils.config import Config

CLIP = ("My name is Donna, and I'm the candidate's mother. I love my daughter, but it's not easy for a mother to say "
        "this: she has a serious problem with the truth.")
READ = ("Find your next fall favorites at Quince. Download the Quince app for app exclusive offers, or go to "
        "quince.com for free shipping on your order.")
T0 = dt(2026, 10, 20, 18, 0)


def filler(tag: str, n: int = 40) -> str:
    return ' '.join(f'{tag}x{i}' for i in range(n))


def transcript(n: int, source: str, *passages: str, hours: float = 0) -> dict:
    """An episode: its own words around the passages, so only the passages are shared"""
    parts = [filler(f'e{n}a')]
    for p in passages:
        parts += [p, filler(f'e{n}b{len(parts)}')]
    return {'id': n, 'source': source, 'title': f'Episode {n}', 'url': f'https://example.com/{n}',
            'published': T0 + td(hours=hours), 'text': ' '.join(parts)}


def segments_of(transcripts: list[dict]):
    """Timed segments as Whisper gives them: ten words each, ten seconds apart"""
    def get(ids):
        out = {}
        for t in transcripts:
            if t['id'] in ids:
                w = t['text'].split()
                out[t['id']] = [{'start': 10.0 * i, 'end': 10.0 * i + 9, 'text': ' '.join(w[j:j + 10])}
                                for i, j in enumerate(range(0, len(w), 10))]
        return out
    return get


# <editor-fold desc="matching">
def test_shingles_hash_each_run_of_k_words_and_match_where_the_words_do():
    a = np.array([1, 2, 3, 4, 5, 6], dtype=np.uint64)
    b = np.array([9, 2, 3, 4, 5, 7], dtype=np.uint64)
    ha, hb = replay.shingles(a, 4), replay.shingles(b, 4)
    assert len(ha) == 3 and len(replay.shingles(a[:3], 4)) == 0
    assert ha[1] == hb[1] and ha[0] != hb[0] and ha[2] != hb[2]
    assert replay.shingles(np.array([2, 1, 3, 4], dtype=np.uint64), 4)[0] != replay.shingles(a[:4], 4)[0]  # order counts


def test_words_lowercase_and_drop_punctuation():
    assert replay.words("I'm the U.S. candidate’s MOTHER!") == ["i'm", 'the', 'u', 's', "candidate's", 'mother']


def test_a_passage_counts_on_three_different_shows_not_three_episodes_of_one():
    ts = [transcript(1, 'psa', CLIP), transcript(2, 'megyn', CLIP), transcript(3, 'megyn', CLIP)]
    kept = [dict(t, words=replay.words(t['text'])) for t in ts]
    assert replay.find(kept) == []
    kept.append(dict(transcript(4, 'upfirst', CLIP), words=None))
    kept[-1]['words'] = replay.words(kept[-1]['text'])
    found = replay.find(kept)
    assert len(found) == 1
    assert found[0]['sources'] == ['megyn', 'psa', 'upfirst'] and sorted(found[0]['episodes']) == [0, 1, 2, 3]
    i, (a, b) = 0, found[0]['episodes'][0][0]
    assert ' '.join(kept[i]['words'][a:b]) == ' '.join(replay.words(CLIP))


def test_a_clip_heard_with_one_word_different_is_put_back_together():
    w = CLIP.split()
    w2 = w[:14] + ['different'] + w[15:]
    ts = [transcript(1, 'psa', CLIP), transcript(2, 'megyn', ' '.join(w2)), transcript(3, 'upfirst', ' '.join(w2)),
          transcript(4, 'pod_rogan', ' '.join(w2))]
    out = replay.build(ts)
    assert len(out) == 1 and out[0]['shows'] == 4
    assert out[0]['words'] >= len(w) - 1


def test_one_episode_listed_twice_by_its_feed_counts_once():
    ts = [transcript(1, 'psa', CLIP), transcript(2, 'megyn', CLIP), transcript(3, 'megyn', CLIP),
          transcript(4, 'upfirst', CLIP)]
    ts[2] = dict(ts[1], id=3)  # the same text again
    assert len(replay.build(ts)[0]['airings']) == 3
# </editor-fold>


# <editor-fold desc="sorting">
def test_classify_says_what_decided_it():
    assert replay.classify('you know ' * 20)[0] == 'glitch'
    assert replay.classify('the u s ' * 10) == ('glitch', '3 different words in 30')
    assert replay.classify("I'm the candidate and I approve this message")[0] == 'campaign'
    assert replay.classify('Paid for by Friends of Someone, not authorized by any candidate') == \
        ('campaign', '"paid for by"')
    assert replay.classify('use promo code AUDIO for twenty percent off') == ('ad', '"promo code"')
    assert replay.classify('book now at visitspc.com') == ('ad', '"at visitspc com"')
    assert replay.classify('everything is priced less than similar brands, high quality not brand markup')[0] == 'ad'
    # Ordinary talk with a stray shopping word or a "go to" is still a clip
    assert replay.classify('Would you accept a peace deal that freezes everything? Then we will go to the '
                           'president and ask for security guarantees') == ('clip', '')
    assert replay.classify(CLIP) == ('clip', '')
    assert replay.classify(READ)[0] == 'ad'


def test_a_piece_broken_off_a_sponsor_read_is_an_ad_too():
    rest = 'The thicker stronger faster growing hair supplement trusted by ten million happy people everywhere'
    ts = [transcript(n, src, READ + ' ' + rest) for n, src in enumerate(['psa', 'megyn', 'upfirst'])]
    # Break the read off its tail with a word heard differently on every show
    for t in ts:
        t['text'] = t['text'].replace('order. The thicker', f'order. zzz{t["id"]} thicker')
    out = replay.build(ts)
    assert out and all(p['kind'] == 'ad' for p in out)


def test_build_gives_each_airing_its_show_lean_and_time_in_the_episode():
    ts = [transcript(1, 'psa', CLIP, hours=0), transcript(2, 'megyn', CLIP, hours=1),
          transcript(3, 'upfirst', CLIP, hours=2)]
    ts[2]['text'] = filler('pad', 25) + ' ' + ts[2]['text']
    (p,) = replay.build(ts, segments_of(ts))
    assert p['kind'] == 'clip' and p['shows'] == 3
    assert [a['show'] for a in p['airings']] == ['Pod Save America', 'The Megyn Kelly Show', 'Up First (NPR)']
    assert [a['group'] for a in p['airings']] == ['left', 'right', 'center']
    assert p['airings'][0]['at'] == 40.0 and p['airings'][2]['at'] == 60.0  # word 40 and word 65, by segment start
    assert p['first'] == '2026-10-20T18:00:00' and p['last'] == '2026-10-20T20:00:00'
    assert p['text'].startswith("My name is Donna, and I'm the candidate's mother.")  # as the transcript has it


def test_episode_time_is_none_past_the_segments():
    segs = [{'start': 0.0, 'text': 'one two three'}, {'start': 5.5, 'text': 'four, five'}]
    assert replay.episode_time(segs, 0) == 0.0 and replay.episode_time(segs, 4) == 5.5
    assert replay.episode_time(segs, 5) is None and replay.episode_time([], 0) is None


def test_as_said_falls_back_to_the_matched_words_when_they_dont_line_up():
    t = {'text': 'Hello, World. Again!', 'words': ['hello', 'world', 'again']}
    assert replay.as_said(t, 0, 2) == 'Hello, World'
    assert replay.as_said(dict(t, words=['hello', 'world']), 0, 2) == 'hello world'


def test_load_recomputes_only_when_the_transcripts_change(tmp_path, monkeypatch):
    ts = [transcript(n, src, CLIP) for n, src in enumerate(['psa', 'megyn', 'upfirst'], 1)]
    rows = [(t['id'], '2026-10-20 18:00:00') for t in ts]
    calls = []
    monkeypatch.setattr(replay, 'cache_path', lambda: str(tmp_path / 'replay.json'))
    monkeypatch.setattr(replay, '_window', lambda: (rows, T0))
    monkeypatch.setattr(replay, '_transcripts', lambda ids: calls.append(ids) or ts)
    monkeypatch.setattr(replay, '_segments', segments_of(ts))
    first = replay.load()
    assert len(first['passages']) == 1 and first['transcripts'] == 3 and first['until'] == '2026-10-20T18:00:00'
    assert replay.load() == first and len(calls) == 1
    rows.append((9, '2026-10-21 00:00:00'))
    replay.load()
    assert len(calls) == 2
# </editor-fold>


# <editor-fold desc="the page">
def test_quote_cuts_with_an_ellipsis_and_marks_a_mid_sentence_start():
    assert page_replay.quote('So he said it, then left.', 3) == 'So he said…'
    assert page_replay.quote('the tally of promises', 10) == '…the tally of promises'
    assert page_replay.quote('i think i know', 10) == 'I think I know'


def test_strip_draws_a_dot_per_airing_in_its_lean_lane():
    ts = [transcript(1, 'psa', CLIP), transcript(2, 'megyn', CLIP, hours=3), transcript(3, 'upfirst', CLIP, hours=30)]
    (p,) = replay.build(ts)
    svg = page_replay.strip(p['airings'])
    soup = BeautifulSoup(svg, 'html.parser')
    dots = soup.select('circle')
    assert len(dots) == 3
    assert {d['fill'] for d in dots} == {page_replay.INK['left'], page_replay.INK['right'], page_replay.INK['center']}
    assert 'viewBox' in svg
    megyn = next(d for d in dots if d['data-tip-head'] == 'The Megyn Kelly Show')  # its hover card's heading
    assert megyn.title.get_text().startswith('Oct 20, 5:00 PM ET\n') and megyn['data-tip-href'] == 'https://example.com/2'


def test_sponsor_reads_are_grouped_by_whether_left_and_right_carried_them():
    def ad(groups):
        return {'text': READ, 'shows': len(groups), 'first': '2026-10-20T18:00:00', 'last': '2026-10-20T18:00:00',
                'why': '"x"', 'airings': [{'source': g, 'show': g, 'group': g, 'url': 'u', 'title': 't',
                                           'published': '2026-10-20T18:00:00', 'at': None} for g in groups]}
    out = page_replay.sponsor_groups([ad(['left', 'center', 'right']), ad(['right']), ad(['center', 'crossover']),
                                      ad(['left', 'right'])])
    assert [(g['key'], len(g['reads'])) for g in out] == [('both', 2), ('right', 1), ('neither', 1)]


def test_the_page_shows_clips_then_sponsor_reads_and_leaves_out_glitches(tmp_path, monkeypatch):
    ts = [transcript(1, 'psa', CLIP, READ), transcript(2, 'megyn', CLIP, READ, hours=1),
          transcript(3, 'upfirst', CLIP, READ, hours=2), transcript(4, 'pod_rogan', 'you know ' * 30, hours=3),
          transcript(5, 'psa', 'you know ' * 30), transcript(6, 'megyn', 'you know ' * 30)]
    passages = replay.build(ts, segments_of(ts))
    assert sorted(p['kind'] for p in passages) == ['ad', 'clip', 'glitch']
    monkeypatch.setattr(replay, 'load', lambda: {'passages': passages, 'transcripts': 6,
                                                 'until': '2026-10-21T00:00:00'})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    page_replay.ReplayPage().generate()
    soup = BeautifulSoup(open(os.path.join(tmp_path, 'replayed.html'), encoding='utf-8').read(), 'html.parser')
    (card,) = soup.select('.replay-card')
    assert card.select_one('.replay-count').get_text(' ', strip=True).startswith('3 shows · 3 airings')
    assert 'Donna' in card.select_one('.replay-quote').get_text()
    assert len(card.select('svg circle')) == 3 and not card.select('a.show-chip')  # the dots' cards name the shows
    assert [li.select_one('a')['href'] for li in card.select('.replay-airings li')] == \
        ['https://example.com/1', 'https://example.com/2', 'https://example.com/3']
    assert 'Quince' in soup.select_one('.replay-reads').get_text()
    assert not any('you know you know' in x.get_text() for x in soup.select('.replay-cards, .replay-reads')) and '1 transcription glitches' in ' '.join(soup.get_text().split())
    assert soup.select_one('nav.navbar a[href="replayed.html"]') is not None


def test_the_page_says_so_when_nothing_was_replayed(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, 'load', lambda: {'passages': [], 'transcripts': 0})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    page_replay.ReplayPage().generate()
    soup = BeautifulSoup(open(os.path.join(tmp_path, 'replayed.html'), encoding='utf-8').read(), 'html.parser')
    assert len(soup.select('.stage-empty')) == 2 and not soup.select('.replay-card')
# </editor-fold>
