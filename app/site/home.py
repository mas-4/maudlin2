import os

import numpy as np
import pandas as pd

from app import j2env
from app.config import Config
from app.constants import Constants
from app.models import Session, Agency, Headline
from app.site.common import generate_wordcloud
from app.logger import get_logger

logger = get_logger(__name__)


class HomePage:
    template = j2env.get_template('index.html')

    def __init__(self):
        self.data = []
        self.urls = {}
        self.agencies = []
        self.metrics = {}
        self.wordcloud_filename = 'wordcloud.png'

    def generate(self):
        logger.info("Generating home page...")
        self.generate_home_wordcloud()
        self.generate_home_data()
        self.render_home_page()
        logger.info("...done")

    def render_home_page(self):
        with open(os.path.join(Config.build, 'index.html'), 'wt') as f:
            f.write(self.template.render(
                title='Home',
                agencies=self.agencies,
                tabledata=self.data,
                urls=self.urls,
                wordcloud=self.wordcloud_filename,
                metrics=self.metrics
            ))

    def generate_home_data(self):
        with Session() as s:
            self.agencies: list[Agency] = s.query(Agency).filter(Agency.articles.any()).order_by(Agency.name).all()
            for agency in self.agencies:
                sentiment = agency.current_compound()
                if np.isnan(sentiment):
                    logger.warning("Sentiment is na for %r.", agency)
                    sentiment = 0
                sentiment = round(sentiment, 2)
                self.data.append(
                    [agency.name, agency.credibility.value, agency.bias.value, str(agency.country), sentiment]
                )
                self.urls[agency.name] = f"{agency.name}.html"
        df = pd.DataFrame(self.data, columns=['Agency', 'Credibility', 'Bias', 'Country', 'Sentiment'])
        us = df[df['Country'] == "United States"]
        self.metrics['median'] = us['Sentiment'].median()
        self.metrics['mean'] = us['Sentiment'].mean()
        self.metrics['partisan_mean'] = (us['Bias'] * us['Sentiment']).mean()

    def generate_home_wordcloud(self):
        with Session() as s:
            generate_wordcloud(
                s.query(Headline).filter(
                    Headline.first_accessed > Constants.TimeConstants.midnight,
                    Headline.last_accessed > Constants.TimeConstants.five_minutes_ago
                ).all(),
                os.path.join(Config.build, self.wordcloud_filename)
            )
