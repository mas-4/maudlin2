from typing import List

from sqlalchemy import ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker
from sqlalchemy.types import Text, Float
from config import Config

class Base(DeclarativeBase):
    pass


class Agency(Base):
    __tablename__ = "agency"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(String(100))
    articles: Mapped[List["Article"]] = relationship("Article", back_populates="user")

    def __repr__(self) -> str:
        return f"Agency(id={self.id!r}, name={self.name!r}, url={self.url!r})"


class Article(Base):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agency.id"))
    user: Mapped["Agency"] = relationship(back_populates="articles")
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


    def __repr__(self) -> str:
        return f"Address(id={self.id!r}, email_address={self.title!r})"

engine = create_engine(Config.connection_string, echo=True)
Base.metadata.create_all(engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)