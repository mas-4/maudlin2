import os
from functools import partial

import pandas as pd
from sqlalchemy import or_

from app.analysis.pipelines import Pipelines, trem, tnorm, STOPWORDS
from app.models import Topic, Session, Article, Headline, Agency
from app.site.common import copy_assets, TemplateHandler
from app.site.graphing import Plots
from app.site.wordcloudgen import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Country
from app.utils.logger import get_logger

logger = get_logger(__name__)
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
    def __init__(self):
        self.context = {'title': 'Topic Analysis'}
        self.template = TemplateHandler('topics.html')
        self.topic_template = TemplateHandler('topic.html')

    def generate(self):
        with Session() as session:
            self.context['topics'] = session.query(Topic).all()
            if not Config.debug:
                for topic in self.context['topics']:
                    self.generate_topic_wordcloud(topic)
        df = self.get_data()
        Plots.topic_history_bar_graph(df.copy())
        Plots.topic_today_bubble_graph(df.copy())
        Plots.topic_today_bar_graph(df.copy())
        Plots.generate_topic_graphs(df, self.context['topics'])
        self.generate_topic_pages(df, self.context['topics'])
        self.template.write(self.context)

    @staticmethod
    def generate_topic_wordcloud(topic: Topic):
        with Session() as session:
            headlines = session.query(Headline.processed).join(Headline.article).filter(
                Article.topic_id == topic.id).all()
            if not headlines:
                return
            topic.wordcloud = f"{topic.name.replace(' ', '_')}_wordcloud.png"
            headlines = [h[0] for h in headlines]
            generate_wordcloud(headlines,
                               os.path.join(Config.build, topic.wordcloud),  # noqa added wordcloud attr above
                               pipeline=PIPELINE)  # noqa added wordcloud attr

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
            if topic_df.empty:
                logger.warning(f"Empty dataframe for {topic.name}")
                continue
            # Sort by last accessed date
            topic_df = topic_df.sort_values('first_accessed', ascending=False)
            topic_df['first_accessed'] = topic_df['first_accessed'].dt.strftime('%Y-%m-%d')
            topic_df['title'] = topic_df.apply(formattitle, axis=1)
            for col in ['afinn', 'vader', 'score']:
                topic_df[col] = topic_df[col].round(2)
            topic_df = topic_df[['id', 'title', 'first_accessed', 'position', 'duration', 'score', 'vader', 'afinn']]
            path = os.path.join(Config.build, f'{topic.name.replace(" ", "_")}.html')
            context = {
                'topic': topic,
                'tabledata': topic_df.values.tolist(),
                'title': topic.name
            }
            self.topic_template.write(context, path)


if __name__ == '__main__':
    Config.debug = True
    copy_assets()
    TopicsPage().generate()
