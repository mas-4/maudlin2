from datetime import datetime as dt

import pandas as pd
from sqlalchemy import ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker
from sqlalchemy.types import Text, Float, DateTime, Integer, Boolean

from app.config import Config
from app.constants import Bias, Credibility, Country


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
    headline_only: Mapped[bool] = mapped_column(Boolean(), default=False)

    columns = ["artneg", "artneu", "artpos", "artcompound", "headneg", "headneu", "headpos", "headcompound"]
    def __repr__(self) -> str:
        return f"Agency(id={self.id!r}, name={self.name!r}, url={self.url!r})"

    def average_sentiment(self):
        with Session() as s:
            numbers = s.query(
                *[getattr(Article, column) for column in self.columns]
            ).filter_by(agency_id=self.id).all()
        return pd.DataFrame(numbers, columns=self.columns).mean()

    def todays_sentiment(self, s=None):
        close = False
        if s is None:
            s = Session()
            close = True
        numbers = s.query(
            *[getattr(Article, column) for column in self.columns]
        ).filter_by(agency_id=self.id).filter(Article.last_accessed > dt.now().date()).all()
        if close:
            s.close()
        return pd.DataFrame(numbers, columns=self.columns).mean().to_frame().T.reset_index(drop=True)

    def todays_compound(self):
        with (Session() as s):
            numbers = s.query(Article.headcompound, Article.artcompound)\
                .filter_by(agency_id=self.id)\
                .filter(Article.last_accessed > dt.now().date())\
                .all()
            df = pd.DataFrame(numbers, columns=["headcompound", "artcompound"]).mean()
        return df["headcompound"], df["artcompound"]

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
    first_accessed: Mapped[dt] = mapped_column(DateTime())
    last_accessed: Mapped[dt] = mapped_column(DateTime())

    def update_last_accessed(self):
        self.last_accessed = dt.now()  # noqa bad pycharm typing


class Article(Base, AccessTimeMixin):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agency.id"))
    agency: Mapped["Agency"] = relationship(Agency, back_populates="articles")
    url: Mapped[str] = mapped_column(String(254))
    failure: Mapped[bool] = mapped_column(Boolean(), default=False)
    headlines: Mapped[list["Headline"]] = relationship("Headline", back_populates="article")

    def __init__(self, **kwargs):
        super().__init__(first_accessed=dt.now(), last_accessed=dt.now(), **kwargs)

    def __repr__(self) -> str:
        return f"Article(id={self.id!r}, agency={self.agency.name!r}, url={self.url!r})"

    def __str__(self) -> str:
        return self.url



class Headline(Base):
    __tablename__ = "headline"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"))
    title: Mapped[str] = mapped_column(Text())

    headneg: Mapped[float] = mapped_column(Float(), nullable=True)
    headneu: Mapped[float] = mapped_column(Float(), nullable=True)
    headpos: Mapped[float] = mapped_column(Float(), nullable=True)
    headcompound: Mapped[float] = mapped_column(Float(), nullable=True)

    article: Mapped["Article"] = relationship(Article, back_populates="headline")

    def __init__(self, **kwargs):
        super().__init__(first_accessed=dt.now(), last_accessed=dt.now(), **kwargs)

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