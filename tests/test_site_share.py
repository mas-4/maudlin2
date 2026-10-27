"""What guests arriving from a shared link get (Oct 27): every page's share tags and address, the share cards, a page
per motif with who its claims came up with, and the Folklore page leaving out donation appeals."""
import os

from bs4 import BeautifulSoup
from PIL import Image

from app.site import common, page_folklore, page_motif, share_images
from app.utils.config import Config


def test_a_page_address_is_the_one_netlify_serves():
    assert common.page_url(os.path.join(Config.build, 'index.html')) == 'https://bignews.day/'
    assert common.page_url(os.path.join(Config.build, 'story-991.html')) == 'https://bignews.day/story-991'
    assert common.page_url(os.path.join(Config.build, 'motif-M619.html')) == 'https://bignews.day/motif-M619'


def test_a_motif_link_goes_to_its_page_or_to_the_index_when_it_has_none(monkeypatch):
    monkeypatch.setitem(common.j2env.globals, 'motif_pages', {'M619'})
    assert common.motif_href('M619') == 'motif-M619.html'
    assert common.motif_href('M742') == 'motifs.html'  # a watch list, or a motif with nothing shown: no page


def test_every_page_carries_share_tags_with_its_own_title_and_address(tmp_path, monkeypatch):
    monkeypatch.setitem(common.j2env.globals, 'site_image', 'share/site-x.png')
    page = common.TemplateHandler('about.html')
    path = os.path.join(Config.build, 'about.html')
    page.write({'title': 'About', 'contact': '', 'og_description': 'What this is.'}, path)
    soup = BeautifulSoup(open(path, encoding='utf-8').read(), 'html.parser')
    meta = {m.get('property') or m.get('name'): m.get('content') for m in soup.find_all('meta')}
    assert meta['og:title'] == 'About · bignews.day'
    assert meta['og:description'] == meta['description'] == 'What this is.'
    assert meta['og:url'] == 'https://bignews.day/about'
    assert meta['og:image'] == 'https://bignews.day/share/site-x.png'
    assert meta['twitter:card'] == 'summary_large_image'


def test_a_share_card_is_drawn_once_and_copied_into_the_build(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'data', str(tmp_path / 'data'))
    monkeypatch.setattr(Config, 'build', str(tmp_path / 'build'))
    first = share_images.motif_card('Lawfare', 'An official turns the law against his enemies.', 'Plots',
                                    {'left': 7, 'center': 3, 'right': 14})
    built = tmp_path / 'build' / first
    assert built.exists()
    assert Image.open(built).size == (share_images.W, share_images.H)
    kept = os.listdir(tmp_path / 'data' / 'share_cache')
    again = share_images.motif_card('Lawfare', 'An official turns the law against his enemies.', 'Plots',
                                    {'left': 7, 'center': 3, 'right': 14})
    assert again == first and os.listdir(tmp_path / 'data' / 'share_cache') == kept
    assert share_images.motif_card('Lawfare', 'Another note.', 'Plots', {}) != first  # a changed card is a new file


def test_a_long_title_is_cut_to_fit_rather_than_spilling_off_the_card(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'data', str(tmp_path / 'data'))
    monkeypatch.setattr(Config, 'build', str(tmp_path / 'build'))
    path = share_images.story_card('word ' * 120, 48, {'left': 19, 'center': 9, 'right': 19}, '15 hours')
    assert Image.open(tmp_path / 'build' / path).size == (share_images.W, share_images.H)


def test_a_motif_came_up_on_each_show_once_by_its_lean():
    entry = {'claims': [{'claim': 'The DOJ targets opponents.', 'source': 'shows', 'ref': 'ep1'},
                        {'claim': 'Democrats want lawfare.', 'source': 'shows', 'ref': 'ep2'},
                        {'claim': 'Omar is persecuted.', 'source': 'narrative'},
                        {'claim': 'Ballots seized.', 'source': 'Snopes'}]}
    key = page_motif.motif_index.key
    tellers = {key('The DOJ targets opponents.'): [{'show': 'Mockler', 'lean': 'left'}, {'show': 'Megyn', 'lean': 'right'}],
               key('Democrats want lawfare.'): [{'show': 'Megyn', 'lean': 'right'}, {'show': 'Jesse Kelly', 'lean': 'right'}]}
    up = page_motif.came_up(entry, tellers, {})
    assert up['shows'] == {'left': ['Mockler'], 'center': [], 'right': ['Jesse Kelly', 'Megyn']}
    assert (up['posts'], up['checkers']) == (1, ['Snopes'])
    assert page_motif.lean_counts(up) == {'left': 1, 'center': 0, 'right': 2}


def test_a_show_claim_no_group_holds_came_up_on_its_own_episode():
    entry = {'claims': [{'claim': 'A one-off.', 'source': 'shows', 'ref': 'https://pod/ep9'}]}
    up = page_motif.came_up(entry, {}, {'https://pod/ep9': {'show': 'Bulwark', 'lean': 'center'}})
    assert up['shows']['center'] == ['Bulwark']


def test_answers_come_first_among_a_motifs_related_motifs():
    index = {'related': [['M1', 'M2'], ['M3', 'M1'], ['M1', 'M9']],
             'related_notes': {'M1|M2': 'sibling: same shape', 'M3|M1': 'No one is above the law answers Lawfare'}}
    shown = {'M1': {'name': 'Lawfare'}, 'M2': {'name': 'Abuse'}, 'M3': {'name': 'No one is above the law'}}
    out = page_motif.related(index, {'id': 'M1'}, shown)
    assert [(r['id'], r['answer']) for r in out] == [('M3', True), ('M2', False)]  # M9 isn't shown: left out


def test_folklore_leaves_out_appeals_for_money_but_not_political_ones():
    assert page_folklore.appeal({'narrative': "A friend's animal charity needs donations for sick pets.", 'politics': False})
    assert not page_folklore.appeal({'narrative': 'Campaigns spam texts asking for donations.', 'politics': True})
    assert not page_folklore.appeal({'narrative': 'Jay-Z will headline the Super Bowl.', 'politics': False})
