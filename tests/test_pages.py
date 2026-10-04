import os

from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_topics import TopicsPage
from app.site.data import DataHandler


def test_headlines_page(data_handler, monkeypatch):
    # Saving and labeling stories writes to the database (shared with production) and calls the llm; stub both
    import app.site.page_headlines as ph
    monkeypatch.setattr(ph, 'sync_stories', lambda df: {})
    monkeypatch.setattr(ph, 'label_stories', lambda df, stories: {})
    monkeypatch.setattr(ph, 'link_sagas', lambda headlines, stories, story_of: {})  # writes sagas to the database
    page = HeadlinesPage(data_handler)
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
