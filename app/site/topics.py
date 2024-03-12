import os
from datetime import datetime as dt
from functools import partial

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from sqlalchemy import or_

from app.analysis.pipelines import Pipelines, trem, tnorm, STOPWORDS
from app.models import Topic, Session, Article, Headline, Agency
from app.site import j2env
from app.site.common import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Country

SPECIAL_DATES = {
    '2024-03-07': "SOTU"
}

stopwords = list(STOPWORDS) + ['ago', 'Ago']

PIPELINE = [
    Pipelines.split_camelcase,
    tnorm.hyphenated_words,
    tnorm.quotation_marks,
    tnorm.unicode,
    tnorm.whitespace,
    trem.accents,
    trem.brackets,
    trem.punctuation,
    Pipelines.tokenize,
    Pipelines.expand_contractions,
    partial(Pipelines.remove_stop, stopwords=stopwords),
    Pipelines.lemmatize,
    lambda x: ' '.join(x)
]


class TopicsPage:
    template = j2env.get_template('topics.html')
    graph_path = 'topics_graph.png'

    def generate(self):
        with Session() as session:
            topics = session.query(Topic).all()
            for topic in topics:
                self.generate_topic_wordcloud(topic)
        df = self.get_data()
        self.generate_graphs(df)
        self.generate_topic_graphs(df, topics)
        with open(os.path.join(Config.build, 'topics.html'), 'wt') as f:
            f.write(self.template.render(topics=topics, graphs_path=self.graph_path, title='Topic Analysis'))

    @staticmethod
    def generate_topic_wordcloud(topic: Topic):
        with Session() as session:
            headlines = session.query(Headline.title).join(Headline.article).filter(Article.topic_id == topic.id).all()
            topic.wordcloud = f"{topic.name.replace(' ', '_')}_wordcloud.png"
            headlines = [h[0] for h in headlines]
            generate_wordcloud(headlines, os.path.join(Config.build, topic.wordcloud), pipeline=PIPELINE)  # noqa added wordcloud attr

    def generate_topic_graphs(self, df, topics):
        for topic in topics:
            topic.graph = f"{topic.name.replace(' ', '_')}_graph.png"
            topic_df = df[df['topic'] == topic.name]
            topic_df['day'] = topic_df['first_accessed'].dt.date
            topic_df = topic_df.groupby('day').agg({
                'sentiment': 'mean',
                'afinn': 'count'
            })
            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot(topic_df.index, topic_df.sentiment, 'r-', label='Sentiment')
            ax.set_xlabel('Date')
            ax.set_ylabel('Sentiment', color='r')
            ax.tick_params(axis='y', labelcolor='r')
            ax2 = ax.twinx()
            ax2.plot(topic_df.index, topic_df.articles, 'b--', label='Articles')
            ax2.set_ylabel('Number of Articles', color='b')
            ax2.tick_params(axis='y', labelcolor='b')

            ax.set_title(f'{topic.name} Sentiment and Number of Articles')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            # rotate x-axis labels
            ax.set_xticks(ax.get_xticks()[::2])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
            for date_str, event in SPECIAL_DATES.items():
                date = dt.strptime(date_str, '%Y-%m-%d').date()
                ax.axvline(date, color='k', linestyle='--', lw=2)
                ax.annotate(event, xy=(date, 20), xytext=(date, 25), ha='center')
            plt.tight_layout()
            plt.savefig(os.path.join(Config.build, topic.graph))

    def generate_graphs(self, df):
        # 4 subplots, 2 rows, 2 columns
        fig, axs = plt.subplots(2, figsize=(9, 8))
        styles = ['r-', 'b--', 'g-.', 'y:', 'c-', 'm--', 'k-.', 'r:', 'b-', 'g--', 'y-.', 'c:', 'm-', 'k--', 'r-.', 'b:']

        for topic, style in zip(df['topic'].unique(), styles):
            topic_df = df[df['topic'] == topic]
            topic_df['day'] = topic_df['first_accessed'].dt.date

            # group by day and calculate average sentiment, emphasis, and number of articles
            topic_df = topic_df.groupby('day').agg({
                'sentiment': 'mean',
                'emphasis': 'mean',
                'afinn': 'count'
            })

            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            axs[0].plot(topic_df.index, topic_df.sentiment, style, label=topic)
            axs[1].plot(topic_df.index, topic_df.articles, style, label=topic)

        axs[0].set_title('Sentiment')
        axs[1].set(yscale='log')
        axs[1].set_title('Number of Articles')
        for ax in axs:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            ax.set_xticks(ax.get_xticks()[::2])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
            ax.legend()
            for date_str, event in SPECIAL_DATES.items():
                date = dt.strptime(date_str, '%Y-%m-%d').date()
                ax.axvline(date, color='k', linestyle='--', lw=2)
                ax.annotate(event, xy=(date, 20), xytext=(date, 25), ha='center')
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, self.graph_path))

    @staticmethod
    def get_data():
        columns = {
            'afinn': Headline.afinn,
            'vader': Headline.vader_compound,
            'position': Headline.position,
            'topic_id': Article.topic_id,
            'topic': Topic.name,
            'first_accessed': Article.first_accessed,
            'last_accessed': Article.last_accessed,
        }
        with (Session() as session):
            data = session.query(*list(columns.values())).join(
                Headline.article
            ).join(Article.topic).join(Article.agency).filter(
                or_(
                    Agency._country == Country.us.value,  # noqa
                    Agency.name.in_(["The Economist", "BBC", "The Guardian"])
                )
            ).all()
        df = pd.DataFrame(data, columns=list(columns.keys()))
        df['duration'] = (df['last_accessed'] - df['first_accessed']).dt.days + 1
        df['sentiment'] = df[['afinn', 'vader']].mean(axis=1)
        df['position'] = 1 / (1 + df['position'])
        df['emphasis'] = df['position'] * df['duration']
        # normalize emphasis
        df['emphasis'] = (df['emphasis'] - df['emphasis'].min()) / (df['emphasis'].max() - df['emphasis'].min())
        # group by topic and last_accessed and calculate average sentiment, emphasis, and number of articles
        return df

if __name__ == '__main__':
    TopicsPage().generate()