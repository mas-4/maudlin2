from app.scraper import GoogleNewsScraper


class WashingtonPost(GoogleNewsScraper):
    """The Post's feed server (feeds.washingtonpost.com) has answered 502 since Oct 17, 2026, and its own site times out
    on us, so we read it through Google News."""
    url: str = 'https://www.washingtonpost.com'
    agency: str = "The Washington Post"
    site = 'washingtonpost.com'
    suffix = ' - The Washington Post'
