import os

from transformers import pipeline as hf_pipeline

from app.analysis.clustering import prepare_cosine, form_clusters, label_clusters
from app.analysis.pipelines import Pipelines, prepare, trem, tnorm
from app.site.common import calculate_xkeyscore, copy_assets, TemplateHandler
from app.site.data import DataHandler, DataTypes
from app.utils.config import Config
from app.utils.constants import Country
from app.utils.logger import get_logger

logger = get_logger(__name__)

summarizer = hf_pipeline('summarization', model='facebook/bart-large-cnn')

pipeline = [
    tnorm.hyphenated_words,
    tnorm.quotation_marks,
    tnorm.unicode,
    tnorm.whitespace,
    trem.accents,
    trem.brackets,
    trem.punctuation,
    str.lower,
    Pipelines.tokenize,
    Pipelines.decontract,
    ' '.join
]


class HeadlinesPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('headlines.html', 'index.html')
        self.newsletter = TemplateHandler('newsletter.html')
        self.context = {'title': 'Current Headlines'}

    def generate(self):
        logger.info("Generating headlines page...")
        df = self.filter_score_sort(self.dh.main_headline_df.copy())
        df = self.cluster_and_summarize(df)
        table_df = self.process_headlines(df)
        self.context['tabledata'] = table_df.values.tolist()
        self.newsletter.write(self.context)
        self.template.write(self.context)
        logger.info("...done")

    def cluster_and_summarize(self, df):
        n_samples_per_cluster = 5
        df['processed'] = df['title'].apply(lambda x: prepare(x, pipeline))
        df = label_clusters(
            df,
            form_clusters(
                prepare_cosine(df['processed']),
                min_samples=n_samples_per_cluster,
                threshold=0.5
            )
        )
        self.summarize(df)
        df['text_length'] = df['processed'].str.len()
        df.sort_values(by='text_length', ascending=False, inplace=True)
        df.drop_duplicates(subset=['cluster', 'agency'], keep='first', inplace=True)
        df = df.groupby('cluster').filter(lambda x: len(x) >= n_samples_per_cluster)
        grouped = df[df['cluster'] != -1].groupby('cluster')
        clusters_list = [{'cluster': key, 'data': group.to_dict(orient='records')} for key, group in grouped]
        clusters_list.sort(key=lambda x: len(x['data']), reverse=True)
        agency_lists = {}
        for cluster in clusters_list:
            cluster['data'].sort(key=lambda x: x['agency'])
            hrefs = []
            for a in sorted(cluster['data'], key=lambda x: x['agency']):
                hrefs.append(f'<a href="{a["url"]}">{a["agency"]}</a>')
            agency_lists[cluster['cluster']] = ', '.join(hrefs)
        self.context['clusters'] = clusters_list
        self.context['agency_lists'] = agency_lists
        return df

    def summarize(self, df):
        # group each cluster, concatenate the processed text, and summarize with nlp
        summaries = {}
        for key, group in df.groupby('cluster'):
            text = ' '.join(group['title'])[:1024]
            summaries[key] = summarizer(text, min_length=10, max_length=50, do_sample=True)[0]['summary_text']
        self.context['summaries'] = summaries

    @staticmethod
    def process_headlines(df):
        def format_title(x):
            t = x.title.replace("'", "").replace('"', '')
            t_trunc = t[:Config.headline_cutoff] + '...' if len(t) > Config.headline_cutoff else t
            return f'<a title="{t}" href="{x.url}">{x.agency} - {t_trunc}</a>'

        df['title'] = df.apply(format_title, axis=1)

        def format_topic(x):
            # Truncate headline_df['title'] to 255 characters and append a ... if it is longer
            if not x.topic:
                return ''
            topic_file = x.topic.replace(' ', '_') + '.html'
            return f'<a href="{topic_file}.html">{x.topic}</a>'

        df['topic'] = df.apply(format_topic, axis=1)
        df = df[
            ['title', 'first_accessed', 'last_accessed', 'score', 'topic', 'vader_compound', 'afinn']
        ]
        df = df.copy().sort_values(by='first_accessed', ascending=False)
        return df

    @staticmethod
    def filter_score_sort(df):
        # if windows:
        fa_str = '%b %-d %-I:%M %p'
        la_str = '%-I:%M %p'
        if os.name == 'nt':  # Windows doesn't like the whole dash thing.
            fa_str = fa_str.replace('-', '')
            la_str = la_str.replace('-', '')
        df['country'] = df['country'].map({c.value: c.name for c in list(Country)})
        df['first_accessed'] = df['first_accessed'].dt.strftime(fa_str)
        df['last_accessed'] = df['last_accessed'].dt.strftime(la_str)
        # drop the sun
        df = df[~(df['agency'] == 'The Sun')]
        return calculate_xkeyscore(df.copy())


if __name__ == '__main__':
    Config.set_debug()
    HeadlinesPage(DataHandler([DataTypes.headlines])).generate()
    copy_assets()
