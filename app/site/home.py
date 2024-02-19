import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns

from app import j2env
from app.config import Config
from app.constants import Constants
from app.models import Session, Agency, Headline, Article
from app.site.common import generate_wordcloud
from app.logger import get_logger
from app.registry import SeleniumScrapers, TradScrapers

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
                agencies=self.agencies,
                tabledata=self.data,
                urls=self.urls,
                metrics=self.metrics,
                FileNames=FileNames
            ))

    def generate_home_data(self):
        with Session() as s:
            scrapers = TradScrapers
            if Config.run_selenium:
                scrapers += SeleniumScrapers
            agency_names = [x.agency for x in scrapers]
            self.agencies: list[Agency] = s.query(Agency).filter(Agency.articles.any(), Agency.name.in_(agency_names))\
                .order_by(Agency.name).all()
            for agency in self.agencies:
                sentiment = agency.current_compound()
                if np.isnan(sentiment):
                    logger.warning("Sentiment is na for %r.", agency)
                    continue
                sentiment = round(sentiment, 2)
                self.data.append(
                    [agency.name, agency.credibility.value, agency.bias.value, str(agency.country), sentiment]
                )
                self.urls[agency.name] = f"{agency.name}.html"
        self.data.sort(key=lambda x: x[4])
        df = pd.DataFrame(self.data, columns=['Agency', 'Credibility', 'Bias', 'Country', 'Sentiment'])
        us = df[df['Country'] == "United States"]
        self.metrics['median'] = us['Sentiment'].median()
        self.metrics['mean'] = us['Sentiment'].mean()
        self.metrics['partisan_mean'] = (us['Bias'] * us['Sentiment']).mean()

    @staticmethod
    def generate_home_wordcloud():
        with Session() as s:
            generate_wordcloud(
                s.query(Headline).filter(
                    Headline.first_accessed > Constants.TimeConstants.midnight,
                    Headline.last_accessed > Constants.TimeConstants.five_minutes_ago
                ).all(),
                str(os.path.join(Config.build, FileNames.wordcloud))
            )

    def render_sentiment_graphs(self):
        with Session() as s:
            data = s.query(Headline.comp, Headline.last_accessed, Agency._bias)\
                .join(Headline.article).join(Article.agency).all()
        df = pd.DataFrame(data, columns=['Sentiment', 'Last Accessed', 'Bias'])
        df['Last Accessed'] = pd.to_datetime(df['Last Accessed'])
        df['PSI'] = df['Sentiment'] * df['Bias']
        agg = df.set_index('Last Accessed').groupby(pd.Grouper(freq='D'))\
            .agg({'Sentiment': ['mean', 'median'], 'PSI': 'mean'}).dropna().reset_index()
        agg.columns = [' '.join(col).strip() for col in agg.columns.values]  # noqa
        agg.rename(columns={'Last Accessed': 'Date'}, inplace=True)

        fig, ax = plt.subplots(2, 2)
        fig.set_size_inches(10, 8)
        sns.lineplot(x='Date', y='Sentiment mean', data=agg, ax=ax[0, 0], label='Mean Sentiment')
        sns.lineplot(x='Date', y='Sentiment median', data=agg, ax=ax[0, 1], label='Median Sentiment')
        sns.lineplot(x='Date', y='PSI mean', data=agg, ax=ax[1, 0], label='Mean Partisan Sentiment Index')
        sns.scatterplot(x='PSI mean', y='Sentiment mean', data=agg, ax=ax[1, 1], label='Mean Sentiment vs PSI')
        for i in range(2):
            for j in range(2):
                if i == 1 and j == 1:
                    continue
                ax[i, j].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
                ax[i, j].set_xticks(ax[i, j].get_xticks()[::2])
                ax[i, j].set_xticklabels(ax[i, j].get_xticklabels(), rotation=45)
        ax[1, 1].set_title('Mean Sentiment vs PSI')
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, FileNames.graphs))




if __name__ == "__main__":
    HomePage().generate()