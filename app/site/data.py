import numpy as np
import pandas as pd

from app.models import Article
from app.models import Session, Agency, Headline
from app.registry import SeleniumScrapers, TradScrapers
from app.utils.config import Config
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from typing import Callable, Optional

logger = get_logger(__name__)


class DataHandler:
    def __init__(self, types: Optional[list[str]] = None):
        logger.info("Initializing DataHandler...")
        if types is None:
            types = ['agency', 'topic', 'headlines']
        if 'agency' in types:
            self.all_sentiment_data = self.aggregate_sentiment_data()
            self.current_processed_headlines = self.get_current_headlines()
            self.agency_data = self.get_agency_data()
            self.agency_metrics = self.agency_metrics(self.agency_data)
        logger.info("DataHandler initialized.")

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
