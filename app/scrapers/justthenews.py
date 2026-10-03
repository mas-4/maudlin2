from app.scraper import FeedScraper


class JustTheNews(FeedScraper):
    url: str = 'https://justthenews.com/'
    agency: str = "Just the News"
    feed: str = 'https://justthenews.com/rss.xml'
