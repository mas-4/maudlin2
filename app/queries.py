from app.models import Headline, Article, Agency
from app.utils.config import Config
from app.utils.constants import Country
from datetime import datetime as dt, timedelta as td
from sqlalchemy import or_

class Queries:
    @staticmethod
    def get_current_headlines(session):
        return (session.query(Headline).join(Headline.article).join(Article.agency)
        .filter(
            or_(
                Agency._country == Country.us.value,  # noqa
                Agency.name.in_(["The Economist", "BBC", "The Guardian"])
            ),
            Headline.last_accessed > Config.last_accessed,
            Headline.first_accessed > dt.now() - td(days=1),
            Headline.position < 25,
        ))

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