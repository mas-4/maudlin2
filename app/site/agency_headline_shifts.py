import os

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt, dates as mdates
from sqlalchemy import func

from app import j2env
from app.models import Agency, Session, Article, Headline
from app.utils.config import Config
from app.utils.constants import Constants


class AgencyHeadlineShiftPages:
    template = j2env.get_template('agency-shift.html')

    def __init__(self, agency: Agency, s: Session):
        self.agency = agency
        self.s: Session = s

    def generate(self):
        articles = self.s.query(Article).filter(Article.agency_id == self.agency.id) \
            .join(Headline, Article.id == Headline.article_id) \
            .filter(Headline.first_accessed > Constants.TimeConstants.yesterday,
                    Headline.last_accessed > Constants.TimeConstants.midnight) \
            .having(func.count(Headline.id) > 5).group_by(Article.id).all()

        for article in articles:
            df = pd.DataFrame([{
                'sentiment': h.vader_compound,
                'date': h.first_accessed,
                'title': h.title,
            } for h in article.headlines])
            if df.sentiment.nunique() <= 1:
                continue
            self.generate_plot(df, article)

    @staticmethod
    def generate_plot(df: pd.DataFrame, article: Article):
        sns.lineplot(data=df, x='date', y='sentiment')
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
        plt.xticks(rotation=45)
        plt.title(f"Sentiment Shift for {article.url}")
        plt.tight_layout()
        filename = article.url.replace('/', '_')
        plt.savefig(os.path.join(Config.build, f"{filename}.png"))
        plt.clf()
