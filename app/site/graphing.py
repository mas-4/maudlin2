import os
from datetime import datetime as dt, timedelta as td

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import dates as mdates
import seaborn as sns

from app.site.common import PathHandler
from app.utils.config import Config
from app.utils.constants import Bias
from app.utils.logger import get_logger

logger = get_logger(__name__)

aisle_colors = {'left': 'blue', 'right': 'red', 'center': 'gray'}
bias_colors = ['#3b4cc0', '#7092f3', '#aac7fd', '#dddddd', '#f7b89c', '#e7755b', '#b40426']
topic_colors = {
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


def get_bottom(df):
    days = (dt.now().date() - df['first_accessed'].min().date()).days + 1
    bottom = pd.DataFrame(pd.date_range(df['first_accessed'].min(), periods=days, freq='D'), columns=['dt'])
    bottom['days'] = bottom['dt'].dt.date
    bottom = bottom.set_index('days')
    bottom['bot'] = 0
    bottom = bottom[['bot']]
    return bottom


def apply_special_dates(ax: plt.Axes, topic):
    ymin, ymax = ax.get_ylim()
    rot = 4
    for i, spdate in enumerate(Config.special_dates):
        if topic != 'all' and spdate.topic != topic:
            continue

        ax.axvline(spdate.date, color=topic_colors[spdate.topic], linestyle='-', lw=1)  # noqa date for float

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


class Plots:
    @staticmethod
    def topic_today_bar_graph(df: pd.DataFrame):
        # adjust timezone for first_accessed from naive utc to eastern
        today_df = df[df['first_accessed'].dt.date == dt.now().date()].sort_values('first_accessed',
                                                                                   ascending=False).copy()
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
        plt.savefig(PathHandler(PathHandler.FileNames.topic_today_bar_graph).build)

    @staticmethod
    def topic_today_bubble_graph(df: pd.DataFrame):
        df = df[df['topic'] != '']
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
                       color=topic_colors[topic], alpha=0.85, edgecolor='none')
        # set horizontal lines at each bias level
        ax.set_title("Today's Articles")
        # x-axis should start at 0:00 and end at 23:59
        ax.yaxis.set_ticks(range(-1, 2))
        ax.yaxis.set_ticklabels(['left', 'center', 'right'])
        # rotate y-axis labels
        ax.set_yticklabels(ax.get_yticklabels(), rotation=45)
        # set x-axis to last night at 11:00 to tonight at 11:00
        ax.set_xlim(dt.now().replace(hour=0, minute=0) - td(hours=1), dt.now().replace(hour=23, minute=59))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.legend()
        plt.tight_layout()
        plt.savefig(PathHandler(PathHandler.FileNames.topic_today_bubble_graph).build)

    @staticmethod
    def topic_history_bar_graph(df: pd.DataFrame):
        df = df[df['topic'] != '']
        fig, ax = plt.subplots()
        fig.set_size_inches(13, 7)
        fig.subplots_adjust(bottom=0.2)

        bottom = get_bottom(df)
        sorted_topics = df.groupby('topic').size().sort_values(ascending=False)
        for i, topic in enumerate(sorted_topics.index):
            topic_df = df[df['topic'] == topic].copy()
            topic_df['day'] = topic_df['first_accessed'].dt.date

            # group by day and calculate average sentiment, emphasis, and number of articles
            topic_df = topic_df.groupby('day').agg({'afinn': 'count'})
            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            if len(topic_df) < len(bottom):
                topic_df = topic_df.reindex(bottom.index, fill_value=0)
            ax.bar(topic_df.index, topic_df.articles, label=topic, bottom=bottom['bot'], color=topic_colors[topic])
            bottom['bot'] += topic_df.articles

        ax.set_title('Number of Articles by Topic Published Per Day')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.set_xticks(ax.get_xticks()[::2])
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles[::-1], labels[::-1])
        apply_special_dates(ax, 'all')
        plt.tight_layout()
        plt.savefig(PathHandler(PathHandler.FileNames.topic_history_bar_graph).build)

    @classmethod
    def individual_topic_graphs(cls, df, topics):
        # blue to red
        df['aisle'] = df['bias'].apply(lambda x: 'left' if x < 0 else 'right' if x > 0 else 'center')
        for topic in topics:
            topic.graph = f"{topic.name.replace(' ', '_')}_graph.png"
            topic_df = df[df['topic'] == topic.name].copy()
            if topic_df.empty:
                logger.warning(f"Empty dataframe for {topic.name}")
                continue
            topic_df['day'] = topic_df['first_accessed'].dt.date

            fig, ax = plt.subplots(figsize=(13, 6))
            cls.individual_topic_article_bar_graph(ax, topic_df)
            cls.individual_topic_sentiment_lines(ax.twinx(), topic_df)

            ax.set_title(f'{topic.name} Sentiment and Number of Articles')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            # rotate x-axis labels
            ax.set_xticks(ax.get_xticks()[::2])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
            apply_special_dates(ax, topic.name)
            plt.legend(loc='upper left')
            plt.tight_layout()
            plt.savefig(os.path.join(Config.build, topic.graph))

    @staticmethod
    def individual_topic_article_bar_graph(ax: plt.Axes, topic_df: pd.DataFrame):
        bottom = get_bottom(topic_df)
        bias_df = topic_df.groupby(['bias', 'day']).agg({
            'afinn': 'count'
        })
        bias_df = bias_df.rename(columns={'afinn': 'articles'})
        for bias in range(-3, 4):
            if bias not in bias_df.index.levels[0]:
                continue
            gdf = bias_df.loc[bias]
            if len(gdf) < len(bottom):
                gdf = gdf.reindex(bottom.index, fill_value=0)
            ax.bar(gdf.index, gdf.articles, color=bias_colors[bias + 3], label=str(Bias(bias)))
            bottom['bot'] += gdf.articles
        ax.set_ylabel('Number of Articles', color='b')
        ax.tick_params(axis='y', labelcolor='b')

    @staticmethod
    def individual_topic_sentiment_lines(ax: plt.Axes, topic_df: pd.DataFrame):
        df = topic_df.groupby(['aisle', 'day']).agg({'sentiment': 'mean'})
        df['sentiment'] = df['sentiment'].rolling(window=7).mean()
        for group in df.index.levels[0]:
            gdf = df.loc[group]
            ax.plot(gdf.index, gdf.sentiment, color=aisle_colors[group], label=group.title())
        ax.axhline(0, color='k', linestyle='dotted', lw=1)
        ax.tick_params(axis='y', labelcolor='r')
        ax.set_xlabel('Date')
        ax.set_ylabel('Sentiment Moving Average', color='r')

    @staticmethod
    def sentiment_graphs(agg):
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
        plt.savefig(PathHandler(PathHandler.FileNames.sentiment_graphs).build)