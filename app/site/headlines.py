import os

import pandas as pd
import pytz
from transformers import pipeline as hf_pipeline

from app.analysis.clustering import prepare_cosine, form_clusters, label_clusters
from app.analysis.pipelines import Pipelines, prepare, trem, tnorm
from app.models import Session, Headline
from app.queries import Queries
from app.site import j2env
from app.site.common import calculate_xkeyscore, copy_assets
from app.utils.config import Config
from app.utils.constants import Constants
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
    template = j2env.get_template('index.html')
    newsletter = j2env.get_template('newsletter.html')

    def generate(self):
        logger.info("Generating headlines page...")
        with Session() as s:
            df = self.get_headlines(s)

        clusters_list, df, summaries, agency_lists = self.get_summaries(df)
        table_df = self.process_headlines(df)

        with open(Config.newsletter, 'wt', encoding='utf8') as f:
            f.write(self.newsletter.render(clusters=clusters_list, summaries=summaries, agency_lists=agency_lists))

        with open(os.path.join(Config.build, 'index.html'), 'wt', encoding='utf8') as f:
            f.write(self.template.render(
                title='Current Headlines',
                tabledata=table_df.values.tolist(),
                clusters=clusters_list,
                summaries=summaries,
                agency_lists=agency_lists
            ))
        logger.info("...done")

    def get_summaries(self, df):
        n_samples_per_cluster = 5
        df['processed'] = df['title'].apply(lambda x: prepare(x, pipeline))
        cosine_sim = prepare_cosine(df['processed'])
        clusters = form_clusters(cosine_sim, min_samples=n_samples_per_cluster, threshold=0.5)
        df = label_clusters(df, clusters)
        # group each cluster, concatenate the processed text, and summarize with nlp
        summaries = {}
        for key, group in df.groupby('cluster'):
            text = ' '.join(group['title'])[:1024]
            summaries[key] = summarizer(text, min_length=10, max_length=30)[0]['summary_text']
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
        return clusters_list, df, summaries, agency_lists

    @staticmethod
    def process_headlines(df):
        def format_title(x):
            t = x.title.replace("'", "").replace('"', '')
            t_trunc = t[:Config.headline_cutoff] + '...' if len(t) > Config.headline_cutoff else t
            return f'<a title="{t}" href="{x.url}">{x.agency} - {t_trunc}</a>'

        df['title'] = df.apply(format_title, axis=1)

        def format_topic(x):
            if not x.topic:
                return ''
            topic_file = x.topic.replace(' ', '_') + '.html'
            return f'<a href="{topic_file}.html">{x.topic}</a>'

        df['topic'] = df.apply(format_topic, axis=1)
        # Truncate headline_df['title'] to 255 characters and append a ... if it is longer
        df = df[
            ['title', 'first_accessed', 'last_accessed', 'score', 'topic', 'vader_compound', 'afinn']
        ]
        df = df.copy().sort_values(by='first_accessed', ascending=False)
        return df

    @staticmethod
    def get_headlines(s):
        headlines: list[Headline] = Queries.get_current_headlines(s).all()
        # if windows:
        if os.name == 'nt':
            fa_str = '%b %d %I:%M %p'
            la_str = '%I:%M %p'
        else:
            fa_str = '%b %-d %-I:%M %p'
            la_str = '%-I:%M %p'

        df = pd.DataFrame([[
            h.processed,
            h.article.agency.name,
            h.first_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone).strftime(fa_str),
            h.last_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone).strftime(la_str),
            h.position,
            round(h.vader_compound, 2),
            round(h.afinn, 2),
            h.article.url,
            h.article.agency.country.name,
            '' if not h.article.topic else h.article.topic.name,
            '' if not h.article.topic else round(h.article.topic_score, 2)
        ] for h in headlines],
            columns=[
                'title',
                'agency',
                'first_accessed',
                'last_accessed',
                'position',
                'vader_compound',
                'afinn',
                'url',
                'country',
                'topic',
                'topic_score'
            ])
        return HeadlinesPage.filter_score_sort(df)

    @staticmethod
    def filter_score_sort(df):
        # drop the sun
        df = df[~(df['agency'] == 'The Sun')]
        return calculate_xkeyscore(df.copy())


if __name__ == '__main__':
    Config.debug = True
    HeadlinesPage().generate()
    copy_assets()
