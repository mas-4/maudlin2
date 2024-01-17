from scraper.scrapers.cnn import CNN

def test_CNN_scraper_instantiation():
    scraper = CNN()
    assert scraper is not None
    assert isinstance(scraper, CNN)