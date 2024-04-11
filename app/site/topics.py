import os
from datetime import datetime as dt, timedelta as td
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
from app.utils.logger import get_logger

logger = get_logger(__name__)



stopwords = list(STOPWORDS) + ['ago', 'Ago']

side_colors = {'left': 'blue', 'right': 'red', 'center': 'gray'}
colors = {
    'War in Gaza': '#005EB8',  # '#1f77b4',           # blue
    'Trump Trial': '#ff7f0e',  # orange
    'Inflation': '#2ca02c',  # green
    'Trump is unfit': '#d62728',  # red
    'Border Chaos': '#9467bd',  # purplish
    'Biden Impeachment': '#8c564b',  # brown
    'Abortion Post-Dobbs': '#e377c2',  # pink
    'Biden is old': '#7f7f7f',  # grey
    'Ukraine': '#FFDD00',  # '#bcbd22',               # yellow
    # '#17becf'  # light blue
}
bias_colors = ['#3b4cc0', '#7092f3', '#aac7fd', '#dddddd', '#f7b89c', '#e7755b', '#b40426']

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
    articles_path = 'current_articles.png'
    today_topic_path = 'current_topics.png'

    def generate(self):
        with Session() as session:
            topics = session.query(Topic).all()
            if not Config.debug:
                for topic in topics:
                    self.generate_topic_wordcloud(topic)
        df = self.get_data()
        self.generate_header_graph(df.copy())
        self.generate_article_scatter(df.copy())
        self.generate_topic_graphs(df, topics)
        self.generate_topic_pages(df, topics)
        self.generate_day_topic_bar_chart(df.copy())
        with open(os.path.join(Config.build, 'topics.html'), 'wt') as f:
            f.write(self.template.render(topics=topics, graphs_path=self.graph_path, articles_path=self.articles_path,
                                         today_topic_path=self.today_topic_path, title='Topic Analysis'))

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
        # blue to red
        df['leftcenter'] = df['bias'].apply(lambda x: 'left' if x < 0 else 'right' if x > 0 else 'center')
        for topic in topics:
            topic.graph = f"{topic.name.replace(' ', '_')}_graph.png"
            topic_df = df[df['topic'] == topic.name].copy()
            topic_df['day'] = topic_df['first_accessed'].dt.date

            fig, ax = plt.subplots(figsize=(13, 6))
            TopicsPage.graph_articles_topic(ax, topic_df)
            TopicsPage.graph_sentiment_lines_topic(ax.twinx(), topic_df)

            ax.set_title(f'{topic.name} Sentiment and Number of Articles')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            # rotate x-axis labels
            ax.set_xticks(ax.get_xticks()[::2])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
            TopicsPage.apply_special_dates(ax, topic.name)
            plt.legend(loc='upper left')
            plt.tight_layout()
            plt.savefig(os.path.join(Config.build, topic.graph))

    @staticmethod
    def graph_articles_topic(ax, topic_df):
        bottom = TopicsPage.get_bottom(topic_df)
        bias_df = topic_df.groupby(['bias', 'day']).agg({
            'afinn': 'count'
        })
        bias_df = bias_df.rename(columns={'afinn': 'articles'})
        # plot a black line at 0
        for bias in range(-3, 4):
            gdf = bias_df.loc[bias]
            if len(gdf) < len(bottom):
                gdf = gdf.reindex(bottom.index, fill_value=0)
            ax.bar(gdf.index, gdf.articles, color=bias_colors[bias + 3], label=str(Bias(bias)))
            bottom['bot'] += gdf.articles
        ax.set_ylabel('Number of Articles', color='b')
        ax.tick_params(axis='y', labelcolor='b')

    @staticmethod
    def graph_sentiment_lines_topic(ax, topic_df):
        df = topic_df.groupby(['leftcenter', 'day']).agg({'sentiment': 'mean'})
        df['sentiment'] = df['sentiment'].rolling(window=7).mean()
        for group in df.index.levels[0]:
            gdf = df.loc[group]
            ax.plot(gdf.index, gdf.sentiment, color=side_colors[group], label=group.title())
        ax.axhline(0, color='k', linestyle='dotted', lw=1)
        ax.tick_params(axis='y', labelcolor='r')
        ax.set_xlabel('Date')
        ax.set_ylabel('Sentiment Moving Average', color='r')

    def generate_day_topic_bar_chart(self, df):
        # adjust timezone for first_accessed from naive utc to eastern
        today_df = df[df['first_accessed'].dt.date == dt.now().date()].sort_values('first_accessed', ascending=False).copy()
        today_df = today_df.groupby(['bias', 'topic']).agg({'afinn': 'count'}).reset_index()
        fig, ax = plt.subplots(figsize=(13, 6))
        left = pd.Series(0, index=today_df['topic'].unique()).sort_index()
        for bias in range(-3, 4):
            gdf = today_df[today_df['bias'] == bias][['topic', 'afinn']].set_index('topic').sort_values('topic')
            if len(gdf) < len(left):
                gdf = gdf.reindex(left.index, fill_value=0)
            ax.barh(gdf.index, gdf['afinn'], color=bias_colors[bias + 3], label=str(Bias(bias)), left=left)
            left += gdf['afinn']
        # set horizontal lines at each bias level
        ax.set_title("Today's Topics")
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, self.today_topic_path))

    def generate_article_scatter(self, df):
        # adjust timezone for first_accessed from naive utc to eastern
        today_df = df[df['first_accessed'].dt.date == dt.now().date()].sort_values('first_accessed',
                                                                                   ascending=False).copy()
        fig, ax = plt.subplots(figsize=(13, 6))
        today_df['side'] = today_df['bias'].apply(lambda x: -1 if x < 0 else 1 if x > 0 else 0)

        for i, topic in enumerate(today_df['topic'].unique()):
            topic_df = today_df[today_df['topic'] == topic].copy()
            # count the number of articles per bias at a given time
            topic_df['hour'] = topic_df['first_accessed'].dt.hour
            topic_df = topic_df.groupby(['hour', 'side']).agg({'afinn': 'count'})
            topic_df = topic_df.rename(columns={'afinn': 'articles'}).reset_index()
            topic_df['hour'] = topic_df['hour'].apply(lambda x: dt.now().replace(hour=x, minute=0))
            topic_df['side'] += i * 0.1
            ax.scatter(topic_df['hour'], topic_df['side'], s=((topic_df['articles']) * 20), label=topic,
                       color=colors[topic], alpha=0.85, edgecolor='none')
        # set horizontal lines at each bias level
        ax.set_title("Today's Articles")
        # x-axis should start at 0:00 and end at 23:59
        ax.yaxis.set_ticks(range(-1,2))
        ax.yaxis.set_ticklabels(['left', 'center', 'right'])
        # rotate y-axis labels
        ax.set_yticklabels(ax.get_yticklabels(), rotation=45)
        # set x-axis to last night at 11:00 to tonight at 11:00
        ax.set_xlim(dt.now().replace(hour=0, minute=0) - td(hours=1), dt.now().replace(hour=23, minute=59))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.legend(loc='upper left')
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, self.articles_path))

    def generate_header_graph(self, df):
        plt.cla()
        plt.clf()
        fig, ax = plt.gcf(), plt.gca()
        fig.set_size_inches(13, 7)
        fig.subplots_adjust(bottom=0.2)

        bottom = TopicsPage.get_bottom(df)
        sorted_topics = df.groupby('topic').size().sort_values(ascending=False)
        for i, topic in enumerate(sorted_topics.index):
            topic_df = df[df['topic'] == topic].copy()
            topic_df['day'] = topic_df['first_accessed'].dt.date

            # group by day and calculate average sentiment, emphasis, and number of articles
            topic_df = topic_df.groupby('day').agg({'afinn': 'count'})
            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            if len(topic_df) < len(bottom):
                topic_df = topic_df.reindex(bottom.index, fill_value=0)
            ax.bar(topic_df.index, topic_df.articles, label=topic, bottom=bottom['bot'], color=colors[topic])
            bottom['bot'] += topic_df.articles

        ax.set_title('Number of Articles by Topic Published Per Day')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.set_xticks(ax.get_xticks()[::2])
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles[::-1], labels[::-1])
        self.apply_special_dates(ax, 'all')
        plt.tight_layout()
        plt.savefig(os.path.join(Config.build, self.graph_path))

    @staticmethod
    def get_bottom(df):
        days = (dt.now().date() - df['first_accessed'].min().date()).days + 1
        bottom = pd.DataFrame(pd.date_range(df['first_accessed'].min(), periods=days, freq='D'), columns=['dt'])
        bottom['days'] = bottom['dt'].dt.date
        bottom = bottom.set_index('days')
        bottom['bot'] = 0
        bottom = bottom[['bot']]
        return bottom

    @staticmethod
    def apply_special_dates(ax: plt.Axes, topic):
        ymin, ymax = ax.get_ylim()
        rot = 4
        for i, spdate in enumerate(Config.special_dates):
            if topic != 'all' and spdate.topic != topic:
                continue

            ax.axvline(spdate.date, color=colors[spdate.topic], linestyle='-', lw=1)  # noqa date for float

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
        # normalize date from utc
        df['first_accessed'] = df['first_accessed'].dt.tz_localize('utc').dt.tz_convert('US/Eastern')
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
    Config.debug = True
    TopicsPage().generate()
