from app.scrapers.npr import NPR


def test_npr():
    """
    We're just testing that the NPR scraper runs without error.
    """
    NPR().run()
