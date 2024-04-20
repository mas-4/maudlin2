import os
from functools import partial

from app.analysis.pipelines import Pipelines, trem, tnorm, STOPWORDS
from app.models import Topic
from app.site.common import copy_assets, TemplateHandler
from app.site.data import DataHandler, DataTypes
from app.site.wordcloudgen import generate_wordcloud
from app.utils.config import Config
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
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.context = {'title': 'Topic Analysis', 'topics': self.dh.topics}
        self.template = TemplateHandler('topics.html')
        self.topic_template = TemplateHandler('topic.html')

    def generate(self):
        if not Config.debug:
            for topic in self.context['topics']:
                self.generate_topic_wordcloud(topic)
        df = self.dh.topic_df
        self.generate_topic_pages(df, self.context['topics'])
        self.template.write(self.context)

    def generate_topic_wordcloud(self, topic: Topic):
        headlines = self.dh.topic_df[self.dh.topic_df['topic'] == topic.name]['headline']
        if not headlines.any():
            return
        topic.wordcloud = f"{topic.name.replace(' ', '_')}_wordcloud.png"
        headlines = [h[0] for h in headlines]
        generate_wordcloud(headlines,
                           os.path.join(Config.build, topic.wordcloud),  # noqa added wordcloud attr above
                           pipeline=PIPELINE)  # noqa added wordcloud attr

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
    Config.set_debug()
    copy_assets()
    TopicsPage(DataHandler([DataTypes.topics])).generate()
