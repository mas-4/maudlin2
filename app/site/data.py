import time
from datetime import timedelta as td
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import or_

from app.models import Session, Agency, Headline, Topic, Article
from app.registry import SeleniumScrapers, TradScrapers
from app.utils.config import Config
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DataTypes(Enum):
    agency = 0
    topics = 1
    headlines = 2


class DataHandler:
    def __init__(self, types: Optional[list[DataTypes]] = None):
        logger.info("Initializing DataHandler...")
        t = time.time()
        if types is None:
            types = list(DataTypes)
        self.main_headline_df = self.get_main_headline_df()
        if DataTypes.agency in types:
            self.all_sentiment_data = self.aggregate_sentiment_data()
            self.current_processed_headlines = self.main_headline_df['title'].tolist()
            self.agency_data = self.get_agency_data()
            self.agency_metrics = self.agency_metrics(self.agency_data)
        if DataTypes.topics in types:
            self.topic_df = self.get_topic_data()
            self.topics = self.get_topics()

        logger.info("DataHandler initialized in %i seconds.", time.time() - t)

    @staticmethod
    def aggregate_sentiment_data():
        with Session() as s:
            data = s.query(
                Headline.vader_compound, Headline.afinn, Headline.last_accessed, Agency._bias  # noqa protected
            ).join(Headline.article).join(Article.agency).all()
        df = pd.DataFrame(data, columns=['Vader', 'Afinn', 'Date', 'Bias'])
        df['Date'] = pd.to_datetime(df['Date'])
        df['PVI'] = df['Vader'] * df['Bias']
        df['PAI'] = df['Afinn'] * df['Bias']
        cols = ['Vader', 'Afinn', 'PVI', 'PAI']
        agg = df.set_index('Date').groupby(pd.Grouper(freq='D')) \
            .agg({col: 'mean' for col in cols}).dropna().reset_index()
        # moving averages for vader and afinn
        agg['Vader MA'] = agg['Vader'].rolling(window=7).mean()
        agg['Afinn MA'] = agg['Afinn'].rolling(window=7).mean()
        agg['PVI MA'] = agg['PVI'].rolling(window=7).mean()
        agg['PAI MA'] = agg['PAI'].rolling(window=7).mean()
        return agg

    @staticmethod
    def get_current_headlines():
        with Session() as s:
            headlines = s.query(Headline.processed).filter(Headline.last_accessed > Config.last_accessed).all()
        return [h[0] for h in headlines]

    @staticmethod
    def get_agency_data():
        with Session() as s:
            scrapers = TradScrapers
            if Config.run_selenium:
                scrapers += SeleniumScrapers
            agencies: list[Agency] = s.query(Agency).filter(
                Agency.articles.any(),
                Agency.name.in_([x.agency for x in scrapers])
            ).order_by(Agency.name).all()
            tabledata = []
            for agency in agencies:
                if np.isnan(vader := round(agency.current_vader(), 2)):
                    logger.warning("Vader is na for %r.", agency)
                    continue
                if np.isnan(afinn := round(agency.current_afinn(), 2)):
                    logger.warning("Afinn is na for %r.", agency)
                    continue
                tabledata.append(
                    [agency.name, str(agency.credibility), str(agency.bias), str(agency.country),
                     round(agency.todays_churn(s), 2), vader, afinn]
                )
        tabledata.sort(key=lambda x: x[-1])
        return tabledata

    @staticmethod
    def agency_metrics(tabledata):
        df = pd.DataFrame(tabledata, columns=['Agency', 'Credibility', 'Bias', 'Country', 'Churn', 'Vader', 'Afinn'])
        df['Bias'] = df['Bias'].map({str(b): b.value for b in list(Bias)})
        df['Credibility'] = df['Credibility'].map({str(c): c.value for c in list(Credibility)})
        us = df[df['Country'] == "United States"]
        return {'median_vader': us['Vader'].median(), 'mean_vader': us['Vader'].mean(),
                'partisan_mean_vader': (us['Bias'] * us['Vader']).mean(),
                'median_afinn': us['Afinn'].median(),
                'mean_afinn': us['Afinn'].mean(),
                'partisan_mean_afinn': (us['Bias'] * us['Afinn']).mean()}

    @staticmethod
    def get_topics():
        with Session() as session:
            return session.query(Topic).all()

    @staticmethod
    def get_topic_data():
        columns = {
            'id': Article.id,
            'headline': Headline.processed,
            'agency': Agency.name,
            'bias': Agency._bias,  # noqa prot attr
            'url': Article.url,
            'afinn': Headline.afinn,
            'vader': Headline.vader_compound,
            'position': Headline.position,
            'topic_id': Article.topic_id,
            'topic': Topic.name,
            'first_accessed': Article.first_accessed,
            'last_accessed': Article.last_accessed,
            'score': Article.topic_score
        }
        with (Session() as session):
            data = session.query(*list(columns.values())).join(
                Headline.article
            ).join(Article.topic).join(Article.agency).filter(
                or_(
                    Agency._country == Country.us.value,  # noqa
                    Agency.name.in_(Config.exempted_foreign_media)
                )
            ).all()
        df = pd.DataFrame(data, columns=list(columns.keys()))
        df['duration'] = (df['last_accessed'] - df['first_accessed']).dt.days + 1
        df['sentiment'] = df[['afinn', 'vader']].mean(axis=1)
        df['positionnorm'] = 1 / (1 + df['position'])
        df['emphasis'] = df['positionnorm'] * df['duration']
        # normalize emphasis
        df['emphasis'] = (df['emphasis'] - df['emphasis'].min()) / (df['emphasis'].max() - df['emphasis'].min())
        # normalize date from utc
        df['first_accessed'] = df['first_accessed'].dt.tz_localize('utc').dt.tz_convert('US/Eastern')
        return df

    @staticmethod
    def get_main_headline_df():
        cols = {
            'article_id': Article.id,
            'title': Headline.processed,
            'agency': Agency.name,
            'bias': Agency._bias,  # noqa prot attr
            'first_accessed': Headline.first_accessed,
            'last_accessed': Headline.last_accessed,
            'position': Headline.position,
            'vader_compound': Headline.vader_compound,
            'afinn': Headline.afinn,
            'url': Article.url,
            'country': Agency._country,  # noqa prot attr
            'topic_id': Article.topic_id,
            'topic': Topic.name,
            'topic_score': Article.topic_score
        }
        with Session() as session:
            data = session.query(
                *list(cols.values())
            ).join(Headline.article).join(Article.agency).join(Article.topic, isouter=True) \
                .filter(
                Headline.last_accessed > Config.last_accessed,
                Headline.first_accessed > Config.last_accessed - td(days=1),
                Headline.position < 25,
            ).order_by(
                Headline.first_accessed.desc(),
                Headline.position.asc()  # prominence
            )
        df = pd.DataFrame(data, columns=list(cols.keys()))

        df['first_accessed'] = df['first_accessed'].dt.tz_localize('utc').dt.tz_convert('US/Eastern')
        df['last_accessed'] = df['last_accessed'].dt.tz_localize('utc').dt.tz_convert('US/Eastern')
        df['vader_compound'] = df['vader_compound'].round(2)
        df['afinn'] = df['afinn'].round(2)

        df['topic'] = df['topic'].fillna('')
        df['topic_score'] = df['topic_score'].round(2)
        return df


if __name__ == '__main__':
    Config.set_debug()
    DataHandler()
