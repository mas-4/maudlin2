import os
from datetime import datetime as dt, timedelta as td

import numpy as np
import pytz
from sklearn.feature_extraction.text import CountVectorizer
import pandas as pd

from app.site import j2env
from app.utils import Config, Constants, get_logger, Country
from app.models import Session, Headline
from app.pipelines import prepare
from app.site.common import pipeline

logger = get_logger(__name__)


class HeadlinesPage:
    template = j2env.get_template('headlines.html')

    def generate(self):
        logger.info("Generating headlines page...")
        with Session() as s:
            headlines = self.get_headlines(s)
            agency_urls, data, urls = self.get_dicts(headlines)
        with open(os.path.join(Config.build, 'headlines.html'), 'wt') as f:
            f.write(self.template.render(
                title='Headlines',
                tabledata=data,
                urls=urls,
                agencyurls=agency_urls
            ))
        logger.info("...done")

    def get_headlines(self, s):
        headlines: list[Headline] = s.query(Headline).filter(
            Headline.last_accessed > Constants.TimeConstants.ten_minutes_ago,
            Headline.first_accessed > dt.now() - td(days=1),
            Headline.position < 25,
        ).order_by(
            Headline.position.asc(),  # prominence
            Headline.first_accessed.desc()
        ).all()

        n_features = 1000
        df = pd.DataFrame([[h.title, h] for h in headlines], columns=['title', 'headline'])
        df['prepared'] = df['title'].apply(lambda x: prepare(x, pipeline=pipeline))
        dense = CountVectorizer(max_features=n_features, ngram_range=(1, 3), lowercase=False).fit_transform(
            df['prepared']
        ).todense()
        top_indices = np.argsort(np.sum(dense, axis=0).A1)[-n_features:]
        df['score'] = [sum(doc[0, i] for i in top_indices if doc[0, i] > 0) for doc in dense]
        return df.sort_values(by='score', ascending=False)['headline'].tolist()

    def get_dicts(self, headlines):
        data = []
        urls = {}
        agency_urls = {}
        for h in headlines:
            if h.article.agency.country not in [Country.us, Country.gb]:
                continue
            if h.article.agency.country == Country.gb and h.article.agency.name not in [
                "The Economist",
                "BBC",
                "The Guardian",
            ]:
                continue
            if h.article.agency.name in ["The Sun", ]:
                continue
            data.append([
                h.title,
                h.article.agency.name,
                h.first_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone) \
                    .strftime('%b %-d %-I:%M %p'),
                h.last_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone) \
                    .strftime('%-I:%M %p'),
                h.position,
                h.vader_compound,
                h.afinn
            ])
            urls[h.title] = h.article.url
            agency_urls[h.article.agency.name] = h.article.agency.url
        return agency_urls, data, urls
