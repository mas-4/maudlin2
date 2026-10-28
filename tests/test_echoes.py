"""Older than you think (Oct 28): approved 1896 echoes of today's motifs, and only approved ones, on their own page"""
from bs4 import BeautifulSoup

from app.analysis import echoes
from app.site import page_echoes, page_trackers


def store(tmp_path, rows):
    path = str(tmp_path / 'archives.sqlite')
    con = echoes.connect(write=True, path=path)
    for i, (status, retold) in enumerate(rows, 1):
        con.execute("insert into echoes (motif, motif_name, claim, run, quote, quote_clean, paper, place, date, url, "
                    "fit, retold, status) values (?, 'Graft', ?, 'A2', 'Tlie bonds were TO go', 'The bonds were to go', "
                    "'The Salt Lake herald. [volume] (Salt Lake City [Utah]) 1870-1909', 'Utah', '1896-01-10', "
                    "'https://chroniclingamerica.loc.gov/x', 1.0, ?, ?)", ('M330', i, retold, status))
    con.commit()
    return path


def test_only_approved_echoes_come_out_the_most_reprinted_first(tmp_path):
    path = store(tmp_path, [('approved', 1), ('proposed', 9), ('rejected', 60), ('approved', 20)])
    got = echoes.approved(path)
    assert [r['retold'] for r in got] == [20, 1] and all(r['status'] == 'approved' for r in got)
    assert echoes.approved(str(tmp_path / 'none.sqlite')) == []  # no table yet: nothing, not an error


def test_paper_names_and_days_read_like_a_masthead():
    assert page_echoes.paper_name('The Salt Lake herald. [volume] (Salt Lake City [Utah]) 1870-1909') == 'The Salt Lake Herald'
    assert page_echoes.paper_name('People&#39;s party paper. [volume] (Atlanta, Ga.) 1891-1898') == "People's Party Paper"
    assert page_echoes.day('1896-01-10') == 'January 10, 1896'


def test_the_page_pairs_2026_with_1896_and_links_the_scan(tmp_path, monkeypatch):
    from app.analysis import motif_index as mi
    from app.site.common import j2env
    from app.utils.config import Config
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    monkeypatch.setitem(j2env.globals, 'icons', {})
    store_path = store(tmp_path, [('approved', 20)])
    real = echoes.approved
    monkeypatch.setattr(echoes, 'approved', lambda path=None: real(store_path))
    entry = {'id': 'M330', 'name': 'Graft', 'note': 'Officials hand contracts to friends.', 'note_by': 'person',
             'done': [], 'facets': {'genre': 'Plots'}, 'claims': [{'claim': 'A 2026 graft claim', 'date': '2026-10-27'}]}
    monkeypatch.setattr(mi, 'load', lambda: {'entries': {'M330': entry}})
    monkeypatch.setattr(mi, 'public_claims', lambda e: e['claims'])
    page_echoes.EchoesPage().generate()
    soup = BeautifulSoup((tmp_path / 'echoes.html').read_text(encoding='utf-8'), 'html.parser')
    card = soup.select_one('.echo-card')
    assert card.select_one('.echo-now h3').get_text(strip=True).endswith('Graft')
    assert 'A 2026 graft claim' in card.select_one('.echo-today').text
    assert card.select_one('.echo-quote').text.strip() == '“The bonds were to go”'
    assert card.select_one('.echo-quote')['data-tip'] == 'Tlie bonds were TO go'  # the OCR as printed, in its card
    assert card.select_one('.echo-scan')['href'] == 'https://chroniclingamerica.loc.gov/x'
    assert 'printed in 20 papers' in card.text and 'The Salt Lake Herald' in card.text
    assert 'checked by a person' in card.select_one('.echo-checked').text  # who checked it, on the card
    assert soup.select_one('.rank-board-viral .rank-row')  # 1896's viral copy, as a strip
    assert not soup.select('.echo-cards [title]')  # details in hover cards, not tooltips


def test_the_menu_leaves_the_page_out_until_an_echo_is_approved(monkeypatch):
    def hrefs():
        return [p['href'] for _, pages, _ in page_trackers.menus(published=True) for p in pages]
    monkeypatch.setattr(echoes, 'any_approved', lambda: False)
    assert 'echoes.html' not in hrefs()
    monkeypatch.setattr(echoes, 'any_approved', lambda: True)
    assert 'echoes.html' in hrefs()
