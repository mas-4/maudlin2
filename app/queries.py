from datetime import datetime as dt, timedelta as td

from sqlalchemy import or_

from app.models import Headline, Article, Agency
from app.utils.config import Config
from app.utils.constants import Country


class Queries:
    @staticmethod
    def get_current_headlines(session):
        base_query = session.query(Headline).join(Headline.article).join(Article.agency)
        country_filter = or_(
            Agency._country == Country.us.value,  # noqa protected
            Agency.name.in_(Config.exempted_foreign_media)
        )
        ordering = [
            Headline.position.asc(),  # prominence
            Headline.first_accessed.desc()
        ]
        if Config.debug:
            return base_query.filter(country_filter, Headline.position < 25).order_by(*ordering).limit(100)
        return base_query.filter(
            country_filter,
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
