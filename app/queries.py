from app.models import Headline, Agency, Article
from app.utils.constants import Constants
from datetime import datetime as dt, timedelta as td

class Queries:
    @staticmethod
    def get_current_headlines(session):
        return session.query(Headline).filter(
            Headline.last_accessed > Constants.TimeConstants.ten_minutes_ago,
            Headline.first_accessed > dt.now() - td(days=1),
            Headline.position < 25,
        )

    @staticmethod
    def get_current_articles(session):
        return session.query(Article).filter(
            Article.last_accessed > Constants.TimeConstants.ten_minutes_ago,
            Article.first_accessed > dt.now() - td(days=1),
        )

    @staticmethod
    def get_todays_articles(session):
        return session.query(Article).filter(
            Article.first_accessed > dt.now() - td(days=1),
            Article.last_accessed > Constants.TimeConstants.midnight,
        )