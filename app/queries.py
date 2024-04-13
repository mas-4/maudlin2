from datetime import datetime as dt, timedelta as td

from app.models import Headline, Article
from app.utils.config import Config


class Queries:
    @staticmethod
    def get_current_headlines(session):
        base_query = session.query(Headline).join(Headline.article).join(Article.agency)
        ordering = [
            Headline.first_accessed.desc(),
            Headline.position.asc()  # prominence
        ]
        if Config.debug:
            return base_query.filter(Headline.position < 25).order_by(*ordering).limit(1000)
        return base_query.filter(
            Headline.last_accessed > Config.last_accessed,
            Headline.first_accessed > dt.now() - td(days=1),
            Headline.position < 25,
        ).order_by(*ordering)

    @staticmethod
    def get_current_articles(session):
        return session.query(Article).filter(
            Article.last_accessed > Config.last_accessed,
            Article.first_accessed > dt.now() - td(days=1),
        )

    @staticmethod
    def get_todays_articles(session):
        return session.query(Article).filter(
            Article.first_accessed > dt.now() - td(days=1),
            Article.last_accessed > Config.last_accessed,
        )
