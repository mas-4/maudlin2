import os
from datetime import datetime as dt, timedelta as td

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import dates as mdates

from app.site.common import PathHandler
from app.utils.config import Config
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)

aisle_colors = {'left': 'blue', 'right': 'red', 'center': 'gray'}
bias_colors = ['#3b4cc0', '#7092f3', '#aac7fd', '#dddddd', '#f7b89c', '#e7755b', '#b40426']
credibility_colors = ["#FF0000", "#FF4500", "#FFA500", "#FFFF00", "#9ACD32", "#008000"]
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
rotation = 35


def get_bottom(df):
    days = (dt.now().date() - df['first_accessed'].min().date()).days + 1
    bottom = pd.DataFrame(pd.date_range(df['first_accessed'].min(), periods=days, freq='D'), columns=['dt'])
    bottom['days'] = bottom['dt'].dt.date
    bottom = bottom.set_index('days')
    bottom['bot'] = 0
    bottom = bottom[['bot']]
    return bottom


def apply_special_dates(ax: plt.Axes, topic):
    ymin, _ = ax.get_ylim()  # Get the minimum y value
    rot = 8  # Adjust rotation if necessary
    i = 0
    for spdate in sorted(Config.special_dates, key=lambda x: x.date, reverse=False):
        if topic != 'all' and spdate.topic != topic:
            continue
        i += 1

        # Calculate offset for text positioning below the x-axis
        # Offset needs to be negative to move the text below the axis
        # Adjust the multiplier (-40, -20 etc.) to position the text appropriately
        offset = -40 - (rot-i % rot) * 13

        # Annotate below the axis
        ax.annotate(
            spdate.name,
            xy=(spdate.date, ymin),  # Position at the bottom of the plot
            xytext=(0, offset),  # Offset text below the x-axis
            textcoords='offset points',
            color=topic_colors[spdate.topic],
            ha='left',
            fontweight='bold',
            zorder=2,
            bbox=dict(facecolor='white', edgecolor='none', alpha=0.8)
        )
        ax.annotate(
            '',
            xy=(spdate.date, ymin),
            xytext=(0, offset),
            textcoords='offset points',
            arrowprops=dict(
                arrowstyle='-',
                linestyle=':',
                color=topic_colors[spdate.topic],
                lw=0.5,
                alpha=0.4
            ),
            zorder=1
        )


class Plots:
    @staticmethod
    def topic_today_bar(df: pd.DataFrame):
        # adjust timezone for first_accessed from naive utc to eastern
        today_df = df[df['first_accessed'].dt.date == dt.now().date()].sort_values(
            'first_accessed', ascending=False
        ).copy()
        today_df = today_df.groupby(['bias', 'topic']).agg({'afinn': 'count'}).reset_index()
        fig, ax = plt.subplots(figsize=(13, 6))
        left = pd.Series(0, index=today_df['topic'].unique()).sort_index()
        for bias in range(-3, 4):
            gdf = today_df[today_df['bias'] == bias][['topic', 'afinn']].set_index('topic').sort_values('topic')
            if len(gdf) < len(left):
                gdf = gdf.reindex(left.index, fill_value=0)
            ax.barh(gdf.index, gdf['afinn'], color=bias_colors[bias + 3], label=str(Bias(bias)), left=left,
                    edgecolor='black')
            left += gdf['afinn']
        # set horizontal lines at each bias level
        ax.set_title("Today's Topics")
        ax.legend(frameon=True, facecolor='lightgray', edgecolor='black', framealpha=0.9, fontsize='medium',
                  title='Bias', title_fontsize='large', fancybox=True, shadow=True, borderpad=1.2, labelspacing=1.5)
        for spine in ['right', 'top', 'left', 'bottom']:
            ax.spines[spine].set_visible(False)
        ax.xaxis.set_visible(False)
        plt.tight_layout()
        plt.savefig(PathHandler(PathHandler.FileNames.topic_today_bar_graph).build)

    @staticmethod
    def topic_today_bubble(df: pd.DataFrame):
        df = df[df['topic'] != '']
        today_df = df[df['first_accessed'].dt.date == dt.now().date()].sort_values(
            'first_accessed',
            ascending=False
        ).copy()
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
                       color=topic_colors[topic], edgecolor='black', alpha=0.45)
        ax.set_title("Today's Articles")
        # x-axis should start at 0:00 and end at 23:59
        ax.yaxis.set_ticks(range(-1, 2))
        ax.yaxis.set_ticklabels(['left', 'center', 'right'])
        # make horizontal lines at the y ticks
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        # rotate y-axis labels
        ax.set_yticklabels(ax.get_yticklabels(), rotation=rotation)
        # set x-axis to last night at 11:00 to tonight at 11:00
        ax.set_xlim(dt.now().replace(hour=0, minute=0) - td(hours=1), dt.now().replace(hour=23, minute=59))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        # rotate x axis 45
        ax.set_xticks(ax.get_xticks()[::2])
        ax.set_xticklabels(ax.get_xticklabels(), rotation=rotation)
        ax.legend(frameon=True, facecolor='lightgray', edgecolor='black', framealpha=0.9, fontsize='medium',
                  title='Topic', title_fontsize='large', fancybox=True, shadow=True, borderpad=1.2,
                  labelspacing=1.5)
        for spine in ['right', 'top', 'left', 'bottom']:
            ax.spines[spine].set_visible(False)
        plt.tight_layout()
        plt.savefig(PathHandler(PathHandler.FileNames.topic_today_bubble_graph).build)

    @staticmethod
    def topic_history_bar(df: pd.DataFrame):
        df = df[df['topic'] != '']
        fig, ax = plt.subplots()
        fig.subplots_adjust(bottom=0.2, top=0.8)  # Adjust top for legend space
        fig.set_size_inches(13, 8)

        # Assuming `get_bottom` is a function that returns a DataFrame with a 'bot' column initialized to zeros
        bottom = get_bottom(df)  # Adjust accordingly
        sorted_topics = df.groupby('topic').size().sort_values(ascending=False)
        for i, topic in enumerate(sorted_topics.index):
            topic_df = df[df['topic'] == topic].copy()
            topic_df['day'] = topic_df['first_accessed'].dt.date

            # Group by day and calculate number of articles
            topic_df = topic_df.groupby('day').agg({'afinn': 'count'})
            topic_df = topic_df.rename(columns={'afinn': 'articles'})
            if len(topic_df) < len(bottom):
                topic_df = topic_df.reindex(bottom.index, fill_value=0)
            ax.bar(topic_df.index, topic_df.articles, label=topic, bottom=bottom['bot'], color=topic_colors[topic],
                   edgecolor='black')
            bottom['bot'] += topic_df.articles

        ax.set_xlim(bottom.index[0] - td(days=1), bottom.index[-1] + td(days=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax.set_xticks(ax.get_xticks()[::2])
        ax.set_xticklabels(ax.get_xticklabels(), rotation=rotation)

        handles, labels = ax.get_legend_handles_labels()
        # Put the legend above the graph, arranged horizontally
        ax.legend(handles[::-1], labels[::-1], loc='lower center', bbox_to_anchor=(0.5, 1.04), ncol=5, frameon=True,
                  facecolor='lightgray', edgecolor='black', framealpha=0.9, fontsize='medium', title_fontsize='large',
                  fancybox=True, shadow=True, borderpad=1.2, labelspacing=1.5)

        for spine in ['right', 'top', 'left', 'bottom']:
            ax.spines[spine].set_visible(False)
        apply_special_dates(ax, 'all')  # Assume this function is defined elsewhere
        plt.tight_layout()
        plt.savefig(PathHandler(
            PathHandler.FileNames.topic_history_bar_graph).build)  # Assume PathHandler is defined elsewhere

    @classmethod
    def individual_topic(cls, df, topics):
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
            cls.individual_topic_article_bar(ax, topic_df)
            cls.individual_topic_sentiment_lines(ax.twinx(), topic_df)

            ax.set_title(f'{topic.name} Sentiment and Number of Articles')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            # rotate x-axis labels
            ax.set_xticks(ax.get_xticks()[::2])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=rotation)
            apply_special_dates(ax, topic.name)
            plt.legend(loc='upper left')
            plt.tight_layout()
            for spine in ['right', 'top', 'left', 'bottom']:
                ax.spines[spine].set_visible(False)
            plt.savefig(os.path.join(Config.build, topic.graph))

    @staticmethod
    def individual_topic_article_bar(ax: plt.Axes, topic_df: pd.DataFrame):
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
            ax.bar(gdf.index, gdf.articles, color=bias_colors[bias + 3], edgecolor='black', label=str(Bias(bias)))
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
                ax[i, j].set_xticklabels(ax[i, j].get_xticklabels(), rotation=rotation)

        plt.tight_layout()
        plt.savefig(PathHandler(PathHandler.FileNames.sentiment_graphs).build)

    @staticmethod
    def agency_distribution(df):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), gridspec_kw={'height_ratios': [5, 1]})

        ###############
        # Plot the credibility groupings
        ###############

        total_counts_by_bias = df['Bias'].value_counts().sort_index()
        # the bottom should start at 0.1
        bottom = pd.Series(np.zeros(len(df['Bias'].unique())), index=df['Bias'].sort_values().unique())
        # Loop through each credibility level
        for n in sorted(df['Credibility'].unique()):
            # Get the counts of bias within this credibility level
            bias_counts = df[df['Credibility'] == n]['Bias'].value_counts().sort_index()
            # Reindex bias_counts to ensure it includes all bias levels (fills missing levels with 0)
            bias_counts = bias_counts.reindex(total_counts_by_bias.index, fill_value=0)
            # Convert counts to percentages of the total counts for each bias level
            percentages = (bias_counts / total_counts_by_bias) * 100

            # Plotting
            ax1.bar(bias_counts.index, percentages, edgecolor='black', bottom=bottom, color=credibility_colors[n],
                    label=str(Credibility(n)), clip_on=False)

            # Update the bottom for the next stack
            bottom += percentages

        # Add a legend to the left
        plt.subplots_adjust(right=1)
        handles, labels = ax1.get_legend_handles_labels()

        # Reverse the order
        handles.reverse()
        labels.reverse()
        ax1.legend(handles, labels, loc='center right', bbox_to_anchor=(0, 0.5), frameon=True, facecolor='lightgray',
                   edgecolor='black', framealpha=0.9, fontsize='medium', title='Credibility',
                   title_fontsize='large', fancybox=True, shadow=True, borderpad=1.2, labelspacing=1.5)

        bias_labels = {b.value: str(b) for b in Bias}
        ax1.set_xticks(list(bias_labels.keys()))
        ax1.set_xticklabels(list(bias_labels.values()), fontsize='large')
        for label, color in zip(ax1.get_xticklabels(), bias_colors):
            label.set_color(color)

        ax1.set_title("Credibility Gap", fontdict={'fontsize': 20})

        ####################
        # Plot the mean credibility within each bias group
        ####################

        # Get the mean credibility for each bias group
        mean_credibility = df.groupby('Bias')['Credibility'].mean()
        # Set a second y-axis with twinx for the credibility that is keyed to the max credibility
        ax3 = ax1.twinx()
        ax3.set_ylim(0, 5)
        # Iterate through the points, plotting a scatter point with the mean credibility of a bias_color
        for i, credibility in mean_credibility.items():
            ax3.scatter(i, credibility, color=bias_colors[i + 3], s=500, edgecolor='black', zorder=10)

        ##########################
        # Plot the bias bar
        ##########################

        base = 0  # Since we only have a single axis we only need a single left value, right?
        bias_counts = df['Bias'].value_counts().sort_index()
        for i in bias_counts.index:
            n = bias_counts[i]
            n = n / bias_counts.sum() * 100  # Get the percentage of the whole
            ax2.barh(' ', n, color=bias_colors[i + 3], edgecolor='black', height=0.5, left=base, label=str(Bias(i)))
            base += n

        # Removing y-ticks
        ax2.set_yticks([])

        # Setting the x-ticks to be percentages
        ax2.set_xticks([0, 20, 40, 60, 80, 100])
        ax2.set_xticklabels(['0%', '20%', '40%', '60%', '80%', '100%'])

        ax2.set_title("A Biased Dataset", fontdict={'fontsize': 20})

        ax2.set_xlim(0, 100)

        for spine in ['right', 'top', 'left', 'bottom']:
            ax1.spines[spine].set_visible(False)
            ax2.spines[spine].set_visible(False)
            ax3.spines[spine].set_visible(False)
        ax1.yaxis.set_visible(False)
        ax2.yaxis.set_visible(False)
        ax3.yaxis.set_visible(False)

        plt.tight_layout()

        plt.savefig(PathHandler(PathHandler.FileNames.agency_distribution).build)
