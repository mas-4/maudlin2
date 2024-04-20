import os

from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_topics import TopicsPage
from app.site.data import DataHandler


def test_headlines_page():
    page = HeadlinesPage()
    page.generate()
    assert os.path.exists(page.template.path)


def test_topics_page(data_handler):
    page = TopicsPage(data_handler)
    page.generate()
    assert os.path.exists(page.template.path)


def test_agencies_page(data_handler: DataHandler):
    page = AgenciesPage(data_handler)
    page.generate()
    assert os.path.exists(page.template.path)
