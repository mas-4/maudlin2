from app.scraper import FeedScraper


class TalkingPointsMemo(FeedScraper):
    url: str = 'https://talkingpointsmemo.com/'
    agency: str = "Talking Points Memo"
    feed: str = 'https://talkingpointsmemo.com/feed'
