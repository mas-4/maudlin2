"""🎯 Its beat (app.analysis.outlet_profile.find_beats): ICA on a made-up coverage table finds the beat two outlets
share, and gives none to a small outlet whose few stories are a mix; the naming; and the outlet page's beat card."""
import re
import zlib

import numpy as np
import pandas as pd
import pytest
from bs4 import BeautifulSoup

from app.analysis import outlet_profile as op
from app.site import page_outlet_map as pom

GENERAL = 140
BEAT = 15
WORDS = ['senate', 'storm', 'court', 'school', 'bridge', 'museum', 'tariff', 'river', 'vaccine', 'airport', 'mayor',
         'factory', 'library', 'harbor', 'festival', 'pipeline', 'satellite', 'orchestra', 'glacier', 'subway',
         'vineyard', 'reactor', 'canal', 'stadium', 'lighthouse', 'monastery', 'refinery', 'volcano', 'zoo', 'opera']


def stand_in_vectors(texts):
    """Bag of hashed words, unit length: labels sharing words come out close"""
    out = np.zeros((len(texts), 512))
    for i, t in enumerate(texts):
        for w in re.findall(r'\w+', t.lower()):
            out[i, zlib.crc32(w.encode()) % 512] += 1
    out[:, 0] += 1e-6
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def table(seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    """27 outlets × 155 stories: everyone runs the general stories (some outlets more than others); 'Alpha' and
    'Beta' also run a beat of 15 baseball stories nobody else much does; 'Small' runs only 20 general stories"""
    rng = np.random.default_rng(seed)
    cols = [f'g{i}' for i in range(GENERAL)] + [f'b{i}' for i in range(BEAT)]
    rows = {}
    for i in range(24):
        p = np.r_[np.full(GENERAL, rng.uniform(0.25, 0.6)), np.full(BEAT, 0.03)]
        rows[f'Outlet {i}'] = rng.random(len(cols)) < p
    for name in ('Alpha', 'Beta'):
        rows[name] = rng.random(len(cols)) < np.r_[np.full(GENERAL, 0.12), np.full(BEAT, 0.95)]
    small = np.zeros(len(cols), bool)
    small[rng.choice(GENERAL, 20, replace=False)] = True
    rows['Small'] = small
    X = pd.DataFrame(rows, index=cols).T.astype(float)
    labels = {f'g{i}': f'{WORDS[i % 30].title()} {WORDS[(7 * i + 3) % 30]} report number {i}' for i in range(GENERAL)}
    labels.update({f'b{i}': f'Rays beat Yankees in game {i} of the baseball series' for i in range(BEAT)})
    return X, pd.Series(labels)


@pytest.fixture(scope='module')
def beats():
    X, labels = table()
    return op.find_beats(X, labels, vectors=stand_in_vectors)


def test_two_outlets_share_the_obvious_beat(beats):
    mine = [b for b in beats if 'Alpha' in b['leaders']]
    assert len(mine) == 1
    beat = mine[0]
    assert set(beat['leaders']) == {'Alpha', 'Beta'}  # both lead it: neither is merely "shared with"
    assert beat['held'] >= op.BEAT_KEEP and beat['coherence'] >= op.BEAT_COHERENT
    assert len(beat['stories']) == op.BEAT_STORIES
    assert all(s['label'].startswith('Rays beat Yankees') for s in beat['stories'])
    assert all(set(s['by']) <= {'Alpha', 'Beta'} and s['by'] for s in beat['stories'])
    assert beat['name'] == 'sport'  # the TOPICS family: 'yankees'


def test_the_small_outlet_with_a_mix_gets_no_beat(beats):
    """A small outlet stands apart in ICA whatever it ran; its mixed stories don't hang together, so no beat"""
    assert not any('Small' in b['leaders'] for b in beats)
    assert not any(o.startswith('Outlet ') for b in beats for o in b['leaders'])


def test_the_small_outlet_does_get_a_component_that_the_coherence_test_drops():
    """The guard is what drops it: without the label test the small outlet would lead a beat of its own"""
    X, labels = table()
    k = min(op.BEAT_K, max(2, len(X) // op.BEAT_PER))
    S, _ = op.ica(X, k, 0)
    top = {X.index[int(np.argmax(S[:, c]))] for c in range(k)}
    assert 'Small' in top


def test_beats_hold_whatever_the_order_of_the_table():
    X, labels = table()
    rng = np.random.default_rng(5)
    shuffled = X.iloc[rng.permutation(len(X)), rng.permutation(X.shape[1])]
    again = op.find_beats(shuffled, labels, vectors=stand_in_vectors)
    assert {frozenset(b['leaders']) for b in again} == {frozenset({'Alpha', 'Beta'})}


def test_no_embedder_means_no_beats():
    X, labels = table()

    def broken(texts):
        raise OSError('no model here')
    assert op.find_beats(X, labels, vectors=broken) == []


def test_a_beat_is_named_only_by_a_topic_well_above_its_usual_share():
    base = {'politics': 0.32, 'crime': 0.14, 'sport': 0.05}
    assert op.beat_name(['Rays win the World Series', 'NFL coach fired', 'Senate vote', 'Storm hits'], base) == 'sport'
    # politics in 3 of 5 is under twice its usual third: no name
    assert op.beat_name(['Senate vote', 'GOP plan', 'Trump rally', 'Storm hits', 'Bridge opens'], base) is None
    assert op.beat_name(['Bridge opens', 'Storm hits'], base) is None


def test_coherence_ranks_a_set_against_random_sets():
    V = stand_in_vectors(['Rays beat Yankees in game one'] * 5 + [f'{w} news' for w in WORDS])
    assert op.coherence(V, np.arange(5)) == 1.0
    assert op.coherence(V, np.arange(5, 10)) < 0.95


# ---- the outlet page

def profile_with_beat() -> dict:
    def fp(x, y, lean, beat=None):
        return {'x': x, 'y': y, 'wire': 0.0, 'heat': 0.0, 'wire_pct': 50, 'heat_pct': 50, 'family': None,
                'type': None, 'like': [], 'is_wire': False, 'lean': lean, 'stories': 30, 'articles': 200, 'beat': beat}
    stories = [{'id': 900 + i, 'label': f'Rays <beat> Yankees in game {i}', 'outlets': 10 - i,
                'by': ['Alpha', 'Beta'] if i != 2 else ['Beta']} for i in range(7)]
    return {'window_days': 28, 'stories': 300, 'articles': 4000,
            'outlets': {'Alpha': fp(0.1, 0.2, 0, 0), 'Beta': fp(0.2, 0.1, None, 0), 'Gamma': fp(-0.3, 0.0, 1),
                        'Delta': fp(0.0, -0.2, -1)},
            'beats': [{'leaders': ['Alpha', 'Beta'], 'name': None, 'held': 0.95, 'coherence': 0.99, 'score': 6.0,
                       'shared': [{'name': 'Gamma', 'ran': 6, 'lift': 7.5}], 'stories': stories}]}


def render_outlet(name: str, profile: dict, with_page: set) -> BeautifulSoup:
    from app.site.common import TemplateHandler
    from app.site.favicons import slug
    o = {'name': name, 'slug': slug(name), 'color': '#00c2a8', 'style': '', 'flag': '🇺🇸', 'country': 'US',
         'headlines': 100, 'live': 10}
    html = TemplateHandler('outlet.html').render({
        'title': name, 'o': o, 'now': {'pack': [], 'only': [], 'stories': 0, 'shown': 12}, 'rewrites': [],
        'window_days': 28, 'fp': pom.fingerprint(profile, name), 'beat': pom.beat_card(profile, name, with_page),
        'profiled': True, 'feelings': None, 'feelings_read': 0, 'measures': [], 'medians': {}})
    return BeautifulSoup(html, 'html.parser')


def test_the_outlet_page_shows_its_beat():
    page = render_outlet('Alpha', profile_with_beat(), with_page={900, 901})
    card = page.select_one('.outlet-beat')
    assert card is not None
    title = ' '.join(card.select_one('.outlet-beat-title').get_text(' ').split())
    # no topic name: the beat is named by its stories, escaped
    assert title.startswith('🎯 Its beat: stories like ‘Rays <beat> Yankees in game 0’ and ‘Rays <beat> Yankees in game 1’')
    assert [a['href'] for a in card.select('.outlet-beat-with a.edit-chip')] == ['outlet-beta.html']
    rows = card.select('.outlet-beat-list .rank-row')
    assert len(rows) == pom.BEAT_SHOWN  # 3 to 5 examples, only the ones it ran
    names = [r.select_one('.rank-name').get_text() for r in rows]
    assert 'Rays <beat> Yankees in game 2' not in names  # Beta's alone
    assert [r.get('href') for r in rows[:3]] == ['story-900.html', 'story-901.html', None]  # a link where a page is
    assert all(r.get('data-tip') and not r.get('title') for r in rows)  # hover cards, never title tooltips
    shared = card.select('.outlet-beat-shared a.edit-chip')
    assert [a['href'] for a in shared] == ['outlet-gamma.html'] and '6 of its 7 stories' in shared[0]['data-tip']
    assert 'rated' not in card.get_text().lower()


def test_an_outlet_without_a_beat_shows_no_card():
    page = render_outlet('Delta', profile_with_beat(), with_page=set())
    assert page.select_one('.outlet-fp') is not None and page.select_one('.outlet-beat') is None


def test_a_named_beat_reads_as_its_topic():
    profile = profile_with_beat()
    profile['beats'][0]['name'] = 'sport'
    card = render_outlet('Beta', profile, with_page=set()).select_one('.outlet-beat')
    assert ' '.join(card.select_one('.outlet-beat-title').get_text(' ').split()).startswith('🎯 Its beat: sport · with')
    assert len(card.select('.outlet-beat-list .rank-row')) == pom.BEAT_SHOWN


def test_the_outlet_map_lists_the_beats():
    rows = pom.beat_rows(profile_with_beat(), {900})
    assert len(rows) == 1 and [c['name'] for c in rows[0]['leaders']] == ['Alpha', 'Beta']
    assert rows[0]['stories'][0]['href'] == 'story-900.html' and len(rows[0]['stories']) == pom.BEAT_SHOWN
