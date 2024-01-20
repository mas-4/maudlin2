from typing import List
from datetime import datetime as dt

from sqlalchemy import ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker
from sqlalchemy.types import Text, Float, DateTime, Integer

from app.config import Config
from app.constants import Bias, Credibility
import pandas as pd


class Base(DeclarativeBase):
    pass


class Agency(Base):
    __tablename__ = "agency"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(String(100))
    articles: Mapped[List["Article"]] = relationship("Article", back_populates="agency", lazy="dynamic")
    _bias: Mapped[int] = mapped_column(Integer())
    _credibility: Mapped[int] = mapped_column(Integer())


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
        return pd.DataFrame(numbers, columns=self.columns).mean()

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

class Article(Base):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_accessed: Mapped[dt] = mapped_column(DateTime())
    last_accessed: Mapped[dt] = mapped_column(DateTime())
    agency_id: Mapped[int] = mapped_column(ForeignKey("agency.id"))
    agency: Mapped["Agency"] = relationship(Agency, back_populates="articles")
    title: Mapped[str] = mapped_column(String(254))
    url: Mapped[str] = mapped_column(String(254))
    body: Mapped[str] = mapped_column(Text())

    artneg: Mapped[float] = mapped_column(Float())
    artneu: Mapped[float] = mapped_column(Float())
    artpos: Mapped[float] = mapped_column(Float())
    artcompound: Mapped[float] = mapped_column(Float())
    headneg: Mapped[float] = mapped_column(Float())
    headneu: Mapped[float] = mapped_column(Float())
    headpos: Mapped[float] = mapped_column(Float())
    headcompound: Mapped[float] = mapped_column(Float())

    def __init__(self, **kwargs):
        super().__init__(first_accessed=dt.now(), last_accessed=dt.now(), **kwargs)

    def update_last_accessed(self):
        self.last_accessed = dt.now()  # noqa bad pycharm typing

    def __repr__(self) -> str:
        return f"Article(id={self.id!r}, agency={self.agency.name!r}, title={self.title!r})"



engine = create_engine(Config.connection_string)
Base.metadata.create_all(engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)