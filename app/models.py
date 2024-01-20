from typing import List
from datetime import datetime as dt

from sqlalchemy import ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker
from sqlalchemy.types import Text, Float, DateTime

from app.config import Config


class Base(DeclarativeBase):
    pass


class Agency(Base):
    __tablename__ = "agency"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(String(100))
    articles: Mapped[List["Article"]] = relationship("Article", back_populates="agency")

    def __repr__(self) -> str:
        return f"Agency(id={self.id!r}, name={self.name!r}, url={self.url!r})"


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