"""app/site/archive.py: dated editions of the front page, in temp folders only."""
import json
import os

import pytest

import app.site.archive as ar
from app.utils import Config

PAGE = """<html><head><link rel="stylesheet" href="./style.css?v=1"><script src="index.js?v=1"></script></head>
<body class="x"><nav><a href="edits.html">changes</a><a href="https://example.com">out</a><a href="#story-3">s</a></nav>
<img src="icons/fox.png"><script>const ICONS = {"Fox News": "icons/fox.png"};</script></body></html>"""


def test_edition_makes_links_absolute_and_adds_a_ribbon():
    out = ar.edition(PAGE, '2026-10-03')
    assert 'href="/style.css?v=1"' in out and 'src="/index.js?v=1"' in out and 'href="/edits.html"' in out
    assert 'href="https://example.com"' in out and 'href="#story-3"' in out  # absolute and in-page links stay
    assert 'src="/icons/fox.png"' in out and '"/icons/fox.png"' in out
    assert '<body class="x"><div class="archive-ribbon">' in out and 'Saturday, October 3, 2026' in out


@pytest.fixture
def folders(tmp_path, monkeypatch):
    build, data = tmp_path / 'build', tmp_path / 'archive'
    build.mkdir()
    monkeypatch.setattr(Config, 'build', str(build))
    monkeypatch.setattr(ar, 'FOLDER', str(data))
    monkeypatch.setattr(ar, 'DAYS', str(data / 'days.json'))
    (build / 'index.html').write_text(PAGE)
    return build, data


def test_debug_builds_never_save(folders, monkeypatch):
    build, data = folders
    monkeypatch.setattr(Config, 'debug', True)
    ar.save({'label': 'Slow news day…'})
    assert not data.exists()


def test_save_then_publish_past_days_only(folders, monkeypatch):
    build, data = folders
    monkeypatch.setattr(Config, 'debug', False)
    monkeypatch.setattr(ar, '_today', lambda: '2026-10-03')
    ar.save({'label': 'Big news day!', 'emoji': '🚨', 'story': 'G7 releases oil', 'stories': 40})
    ar.publish()
    assert not (build / '2026' / '10' / '03').exists()  # today's edition isn't finished
    monkeypatch.setattr(ar, '_today', lambda: '2026-10-04')
    ar.publish()
    edition = (build / '2026' / '10' / '03' / 'index.html').read_text()
    assert 'archive-ribbon' in edition
    listing = (build / 'archive.html').read_text()
    assert '/2026/10/03/' in listing and 'G7 releases oil' in listing
    assert json.loads((data / 'days.json').read_text())['2026-10-03']['stories'] == 40
