from scraper.scrapers.cnn import CNNScraper

def test_CNN_scraper_instantiation():
    scraper = CNNScraper()
    assert scraper is not None
    assert isinstance(scraper, CNNScraper)