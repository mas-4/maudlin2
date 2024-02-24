from datetime import datetime as dt, timedelta as td

import numpy as np
import pytz
from sqlalchemy import ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker
from sqlalchemy.types import Text, Float, DateTime, Integer

from app.utils import Config, Bias, Credibility, Country, get_logger

logger = get_logger(__name__)

class Base(DeclarativeBase):
    pass


class Agency(Base):
    __tablename__ = "agency"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(String(100))
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="agency", lazy="dynamic")
    _bias: Mapped[int] = mapped_column(Integer())
    _credibility: Mapped[int] = mapped_column(Integer())
    _country: Mapped[int] = mapped_column(Integer())

    columns = ["headneg", "headneu", "headpos", "headcompound"]

    def __repr__(self) -> str:
        return f"Agency(id={self.id!r}, name={self.name!r}, url={self.url!r})"

    def current(self, col) -> float:
        with (Session() as s):
            first_date = s.query(Article.first_accessed) \
                .filter_by(agency_id=self.id) \
                .order_by(Article.first_accessed.asc()).first()[0]
            numbers = np.array(s.query(col) \
                .join(Article, Article.id == Headline.article_id) \
                .filter_by(agency_id=self.id) \
                .filter(
                    Article.first_accessed > first_date + td(days=1),  # This is to eliminate permanent links
                    Article.last_accessed > Config.last_accessed  # we want current articles!
                ).all()).flatten()
        if np.isnan(np.mean(numbers)):
            logger.warning("No %s data for %r.", col, self)
        return np.mean(numbers[~np.isnan(numbers)])

    def current_vader(self) -> float:
        return self.current(Headline.vader_compound)

    def current_afinn(self) -> float:
        return self.current(Headline.afinn)



    @property
    def bias(self):
        return Bias(self._bias)

    @bias.setter
    def bias(self, value):
        self._bias = value.value

    @property
    def credibility(self):
        return Credibility(self._credibility)

    @credibility.setter
    def credibility(self, value):
        self._credibility = value.value

    @property
    def country(self):
        return Country(self._country)

    @country.setter
    def country(self, value):
        self._country = value.value


class AccessTimeMixin:
    first_accessed: Mapped[dt] = mapped_column(DateTime(), default=dt.now(pytz.UTC))
    last_accessed: Mapped[dt] = mapped_column(DateTime(), default=dt.now(pytz.UTC))

    def update_last_accessed(self):
        self.last_accessed = dt.now(pytz.UTC) # noqa type: ignore


class Article(Base, AccessTimeMixin):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agency.id"))
    agency: Mapped["Agency"] = relationship(Agency, back_populates="articles")
    url: Mapped[str] = mapped_column(String(254))
    headlines: Mapped[list["Headline"]] = relationship("Headline", back_populates="article")


    def __repr__(self) -> str:
        return f"Article(id={self.id!r}, agency={self.agency.name!r}, url={self.url!r})"

    def __str__(self) -> str:
        return self.url


class Headline(Base, AccessTimeMixin):
    __tablename__ = "headline"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"))
    article: Mapped["Article"] = relationship(Article, back_populates="headlines")
    title: Mapped[str] = mapped_column(Text())
    position: Mapped[int] = mapped_column(Integer(), default=0, nullable=True)

    vader_neg: Mapped[float] = mapped_column(Float(), nullable=True)
    vader_neu: Mapped[float] = mapped_column(Float(), nullable=True)
    vader_pos: Mapped[float] = mapped_column(Float(), nullable=True)
    vader_compound: Mapped[float] = mapped_column(Float(), nullable=True)
    afinn: Mapped[float] = mapped_column(Float(), nullable=True)

    def __repr__(self) -> str:
        return f"Headline(id={self.id!r}, agency={self.article.agency.name!r}, title={self.title!r})"

    def __str__(self) -> str:
        return self.title


engine = create_engine(Config.connection_string)
# Keeping this after migrating to alembic
# Running this would create the tables in the database but not mark alembic upgrades
# So just don't do it. To upgrade the database run alembic upgrade head
# Base.metadata.create_all(engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
