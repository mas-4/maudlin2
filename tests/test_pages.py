import os

from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_topics import TopicsPage


def test_headlines_page():
    page = HeadlinesPage()
    page.generate()
    assert os.path.exists(page.template.path)


def test_topics_page():
    page = TopicsPage()
    page.generate()
    assert os.path.exists(page.template.path)


def test_agencies_page():
    page = AgenciesPage()
    page.generate()
    assert os.path.exists(page.template.path)