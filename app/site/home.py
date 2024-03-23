import os

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from app.models import Session, Agency, Headline, Article
from app.registry import SeleniumScrapers, TradScrapers
from app.site import j2env
from app.site.common import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Constants, Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FileNames:
    wordcloud = 'wordcloud.png'
    graphs = 'graphs.png'


class HomePage:
    template = j2env.get_template('index.html')

    def __init__(self):
        self.data = []
        self.urls = {}
        self.agencies = []
        self.metrics = {}

    def generate(self):
        logger.info("Generating home page...")
        self.generate_home_wordcloud()
        self.generate_home_data()
        self.render_sentiment_graphs()
        self.render_home_page()
        logger.info("...done")

    def render_home_page(self):
        with open(os.path.join(Config.build, 'index.html'), 'wt') as f:
            f.write(self.template.render(
                title='Home',
                tabledata=self.data,
                urls=self.urls,
                metrics=self.metrics,
                FileNames=FileNames,
                bias={str(b): b.value for b in list(Bias)},
                credibility={str(c): c.value for c in list(Credibility)}
            ))

    def generate_home_data(self):
        with Session() as s:
            scrapers = TradScrapers
            if Config.run_selenium:
                scrapers += SeleniumScrapers
            self.agencies: list[Agency] = s.query(Agency).filter(
                Agency.articles.any(),
                Agency.name.in_([x.agency for x in scrapers])
            ).order_by(Agency.name).all()
            self.data = []
            for agency in self.agencies:
                if np.isnan(vader := round(agency.current_vader(), 2)):
                    logger.warning("Vader is na for %r.", agency)
                    continue
                if np.isnan(afinn := round(agency.current_afinn(), 2)):
                    logger.warning("Afinn is na for %r.", agency)
                    continue
                self.data.append(
                    [agency.name, str(agency.credibility), str(agency.bias), str(agency.country),
                     round(agency.todays_churn(s), 2), vader, afinn]
                )
                self.urls[agency.name] = f"{agency.name}.html"
        self.data.sort(key=lambda x: x[-1])
        df = pd.DataFrame(self.data, columns=['Agency', 'Credibility', 'Bias', 'Country', 'Churn', 'Vader', 'Afinn'])
        df['Bias'] = df['Bias'].map({str(b): b.value for b in list(Bias)})
        df['Credibility'] = df['Credibility'].map({str(c): c.value for c in list(Credibility)})
        us = df[df['Country'] == "United States"]
        self.metrics['median_vader'] = us['Vader'].median()
        self.metrics['mean_vader'] = us['Vader'].mean()
        self.metrics['partisan_mean_vader'] = (us['Bias'] * us['Vader']).mean()
        self.metrics['median_afinn'] = us['Afinn'].median()
        self.metrics['mean_afinn'] = us['Afinn'].mean()
        self.metrics['partisan_mean_afinn'] = (us['Bias'] * us['Afinn']).mean()

    @staticmethod
    def generate_home_wordcloud():
        with Session() as s:
            logger.info("Querying data for home wordcloud...")
            titles = s.query(Headline.title).filter(
                Headline.first_accessed > Constants.TimeConstants.midnight,
                Headline.last_accessed > Config.last_accessed
            ).all()
            logger.info("...done")
            path = str(os.path.join(Config.build, FileNames.wordcloud))
            logger.info("Calling generate_wordcloud...")
            generate_wordcloud(titles, path)
            logger.info("..done")

    def render_sentiment_graphs(self):
        with Session() as s:
            data = s.query(
                Headline.vader_compound, Headline.afinn, Headline.last_accessed, Agency._bias  # noqa protected
            ).join(Headline.article).join(Article.agency).all()
        self.generate_graphs(self.aggregate_data(data))

    @staticmethod
    def generate_graphs(agg):
        fig, ax = plt.subplots(2, 2)
        fig.set_size_inches(9, 8)
        sns.lineplot(x='Date', y='Vader', data=agg, ax=ax[0, 0], label='Mean VADER')
        sns.lineplot(x='Date', y='Vader MA', data=agg, ax=ax[0, 0], label='Moving Average')
        sns.lineplot(x='Date', y='PVI', data=agg, ax=ax[0, 1], label='PVI (-left/+right)')
        sns.lineplot(x='Date', y='PVI MA', data=agg, ax=ax[0, 1], label='Moving Average')
        sns.lineplot(x='Date', y='Afinn', data=agg, ax=ax[1, 0], label='Mean AFINN')
        sns.lineplot(x='Date', y='Afinn MA', data=agg, ax=ax[1, 0], label='Moving Average')
        sns.lineplot(x='Date', y='PAI', data=agg, ax=ax[1, 1], label='PAI (-left/+right)')
        sns.lineplot(x='Date', y='PAI MA', data=agg, ax=ax[1, 1], label='Moving Average')
        for i in range(2):
            for j in range(2):
                ax[i, j].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
                ax[i, j].set_xticks(ax[i, j].get_xticks()[::2])
                ax[i, j].set_xticklabels(ax[i, j].get_xticklabels(), rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, FileNames.graphs))

    @staticmethod
    def aggregate_data(data):
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


if __name__ == "__main__":
    HomePage().generate()
