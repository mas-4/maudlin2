"""Podcast episodes whose feed gave no link keep their guid as their url; pages must link the audio instead (Oct 31)"""
from app import sidefeeds


def test_an_address_stays_and_a_guid_becomes_its_audio():
    assert sidefeeds.web_link('https://example.com/ep1', 'https://cdn/ep1.mp3') == 'https://example.com/ep1'
    assert sidefeeds.web_link('4dfe26c6-b04c-11f0-b0cb-5f58b948bb5e', 'https://cdn/ep1.mp3') == 'https://cdn/ep1.mp3'
    assert sidefeeds.web_link('4dfe26c6', None) == '4dfe26c6'


def test_a_page_links_the_audio_not_the_guid(monkeypatch):
    monkeypatch.setattr(sidefeeds, '_EPISODES', {'4dfe26c6-b04c': 'https://cdn/a.mp3?x=1&y=2'})
    page = ('<a href="4dfe26c6-b04c">ep</a> <a href="tv.html">tv</a> <a href="https://x.com/a">x</a> '
            '<a href="#top">top</a> <a href="/archive.html">all</a> <link href="style.css">')
    out = sidefeeds.fix_episode_links(page)
    assert '<a href="https://cdn/a.mp3?x=1&amp;y=2">ep</a>' in out
    assert out.replace('<a href="https://cdn/a.mp3?x=1&amp;y=2">ep</a>', '') == \
        page.replace('<a href="4dfe26c6-b04c">ep</a>', '')
