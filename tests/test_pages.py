import os

import pytest

from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.data import DataHandler


# Whole pages on the real database: about 75 s together, and the hourly build makes the same pages for real, so the
# commit hook leaves them out (pytest -m slow runs them)
@pytest.mark.slow
def test_headlines_page(data_handler, monkeypatch):
    # Saving and labeling stories writes to the database (shared with production) and calls the llm; stub both
    import app.site.page_headlines as ph
    monkeypatch.setattr(ph, 'sync_stories', lambda df: {})
    monkeypatch.setattr(ph, 'label_stories', lambda df, stories: {})
    monkeypatch.setattr(ph, 'link_sagas', lambda headlines, stories, story_of: {})  # writes sagas to the database
    page = HeadlinesPage(data_handler)
    page.generate()
    assert os.path.exists(page.template.path)


@pytest.mark.slow
def test_agencies_page(data_handler: DataHandler):
    page = AgenciesPage(data_handler)
    page.generate()
    assert os.path.exists(page.template.path)
