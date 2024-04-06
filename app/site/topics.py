import os
from functools import partial

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import or_

from app.analysis.pipelines import Pipelines, trem, tnorm, STOPWORDS
from app.models import Topic, Session, Article, Headline, Agency
from app.site import j2env
from app.site.common import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Country, Bias


stopwords = list(STOPWORDS) + ['ago', 'Ago']

PIPELINE = [
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
    topic_template = j2env.get_template('topic.html')
    graph_path = 'topics_graph.png'

    def generate(self):
        with Session() as session:
            topics = session.query(Topic).all()
            #for topic in topics:
            #    self.generate_topic_wordcloud(topic)
        df = self.get_data()
        self.generate_header_graph(df)
        self.generate_topic_graphs(df, topics)
        self.generate_topic_pages(df, topics)
        with open(os.path.join(Config.build, 'topics.html'), 'wt') as f:
            f.write(self.template.render(topics=topics, graphs_path=self.graph_path, title='Topic Analysis'))

    @staticmethod
    def generate_topic_wordcloud(topic: Topic):
        with Session() as session:
            headlines = session.query(Headline.processed).join(Headline.article).filter(
                Article.topic_id == topic.id).all()
            topic.wordcloud = f"{topic.name.replace(' ', '_')}_wordcloud.png"
            headlines = [h[0] for h in headlines]
            generate_wordcloud(headlines,
                               os.path.join(Config.build, topic.wordcloud),  # noqa added wordcloud attr above
                               pipeline=PIPELINE)  # noqa added wordcloud attr

    @staticmethod
    def generate_topic_graphs(df, topics):
        colors = ['#3b4cc0', '#7092f3', '#aac7fd', '#dddddd', '#f7b89c', '#e7755b', '#b40426']
        for topic in topics:
            topic.graph = f"{topic.name.replace(' ', '_')}_graph.png"
            topic_df = df[df['topic'] == topic.name].copy()
            topic_df['day'] = topic_df['first_accessed'].dt.date
            topic_df = topic_df.groupby(['bias', 'day']).agg({
                'sentiment': 'mean',
                'afinn': 'count'
            })
            topic_df['sentiment'] = topic_df['sentiment'].rolling(window=7).mean()
            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            fig, ax = plt.subplots(figsize=(13, 6))
            for bias in topic_df.index.levels[0]:
                gdf = topic_df.loc[bias]
                ax.plot(gdf.index, gdf.sentiment, color=colors[bias+3], label='Sentiment')
            ax.set_xlabel('Date')
            ax.set_ylabel('Sentiment Moving Average', color='r')
            ax.tick_params(axis='y', labelcolor='r')
            ax2 = ax.twinx()
            for bias in topic_df.index.levels[0]:
                gdf = topic_df.loc[bias]
                enum = Bias(bias)
                ax2.bar(gdf.index, gdf.articles, color=colors[bias+3], alpha=0.75, label=str(enum))
            ax2.set_ylabel('Number of Articles', color='b')
            ax2.tick_params(axis='y', labelcolor='b')

            ax.set_title(f'{topic.name} Sentiment and Number of Articles')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            # rotate x-axis labels
            ax.set_xticks(ax.get_xticks()[::2])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
            TopicsPage.apply_special_dates(ax2, topic.name)
            plt.legend(loc='upper left')
            plt.tight_layout()
            plt.savefig(os.path.join(Config.build, topic.graph))

    def generate_header_graph(self, df):
        plt.cla()
        plt.clf()
        fig, ax = plt.gcf(), plt.gca()
        fig.set_size_inches(13, 7)

        for topic in df['topic'].unique():
            topic_df = df[df['topic'] == topic].copy()
            topic_df['day'] = topic_df['first_accessed'].dt.date

            # group by day and calculate average sentiment, emphasis, and number of articles
            topic_df = topic_df.groupby('day').agg({'afinn': 'count'})

            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            ax.bar(topic_df.index, topic_df.articles, label=topic)

        ax.set_title('Number of Articles by Topic Published Per Day')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.set_xticks(ax.get_xticks()[::2])
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
        ax.legend(loc='upper left')
        self.apply_special_dates(ax, 'all')
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, self.graph_path))

    @staticmethod
    def apply_special_dates(ax: plt.Axes, topic):
        ymin, ymax = ax.get_ylim()
        rot = 4
        for i, spdate in enumerate(Config.special_dates):
            if topic != 'all' and spdate.topic != topic:
                continue
            ax.axvline(spdate.date, color='k', linestyle='--', lw=2)  # noqa date for float

            offset = (i % rot) * ((ymax + ymin - 20) / rot)
            ax.annotate(
                spdate.name,
                xy=(spdate.date, offset),  # noqa date for float
                xytext=(0, 20),
                textcoords='offset points',
                ha='right',
                fontsize=12,
                color='black',
                fontweight='bold',
                arrowprops=dict(
                    facecolor='red',
                    arrowstyle='->',
                    linewidth=2
                )
            )

    @staticmethod
    def get_data():
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
        return df

    def generate_topic_pages(self, df, topics):
        def formattitle(x):
            t = x.headline.replace("'", "").replace('"', '')
            t_trunc = x.headline[:Config.headline_cutoff] + '...' if len(
                x.headline) > Config.headline_cutoff else x.headline
            return f'<a title="{t}" href="{x.url}">{x.agency} - {t_trunc}</a>'

        for topic in topics:
            topic_df = df[df['topic'] == topic.name]
            # Sort by last accessed date
            topic_df = topic_df.sort_values('first_accessed', ascending=False)
            topic_df['first_accessed'] = topic_df['first_accessed'].dt.strftime('%Y-%m-%d')
            topic_df['title'] = topic_df.apply(formattitle, axis=1)
            for col in ['afinn', 'vader', 'score']:
                topic_df[col] = topic_df[col].round(2)
            topic_df = topic_df[['id', 'title', 'first_accessed', 'position', 'duration', 'score', 'vader', 'afinn']]
            with open(os.path.join(Config.build, f'{topic.name.replace(" ", "_")}.html'), 'wt') as f:
                f.write(self.topic_template.render(topic=topic, tabledata=topic_df.values.tolist(), title=topic.name))


if __name__ == '__main__':
    TopicsPage().generate()
