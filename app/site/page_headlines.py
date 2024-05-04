import os

from transformers import pipeline as hf_pipeline

from app.analysis.clustering import prepare_cosine, form_clusters, label_clusters
from app.analysis.pipelines import Pipelines, prepare, trem, tnorm
from app.site.common import calculate_xkeyscore, copy_assets, TemplateHandler
from app.site.data import DataHandler, DataTypes
from app.site.graphing import bias_colors
from app.utils import Config, Country, get_logger

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
        self.cluster_and_summarize(df.copy())
        table_df = self.process_headlines(df)
        self.context['tabledata'] = table_df.values.tolist()
        self.newsletter.write(self.context)
        self.template.write(self.context)
        logger.info("...done")

    def cluster_and_summarize(self, df):
        n_samples_per_cluster = 10
        df = df[
            (df['country'] == Country.us.name)
            |
            (
                    (df['country'] == Country.gb.name)
                    &
                    (df['agency'].isin(Config.exempted_foreign_media))
            )
            ].copy()
        df['processed'] = df['title'].apply(lambda x: prepare(x, pipeline))
        df = label_clusters(
            df,
            form_clusters(
                prepare_cosine(df['processed']),
                min_samples=n_samples_per_cluster,
                threshold=0.5
            )
        )
        df = df[df['cluster'] != -1].copy()
        df.drop_duplicates(subset=['cluster', 'agency'], keep='first', inplace=True)
        df['text_length'] = df['title'].str.len()
        df.sort_values(by='text_length', ascending=False, inplace=True)
        df = df.groupby('cluster').filter(lambda x: len(x) >= n_samples_per_cluster)
        logger.info("%i clusters left after filtering", df['cluster'].nunique())
        self.summarize(df)
        grouped = df.groupby('cluster')
        clusters_list = [{'cluster': key, 'data': group.to_dict(orient='records')} for key, group in grouped]
        clusters_list.sort(key=lambda x: len(x['data']), reverse=True)
        self.make_agency_lists(clusters_list)
        self.context['clusters'] = clusters_list

    def make_agency_lists(self, clusters_list):
        agency_lists = {}
        for cluster in clusters_list:
            cluster['data'].sort(key=lambda x: x['agency'])
            hrefs = []
            last_bias = -3
            for a in sorted(cluster['data'], key=lambda x: x['bias']):
                if a['bias'] != last_bias:
                    hrefs.append(f'<br>')
                    last_bias = a['bias']
                mean_sentiment = (a['afinn'] + a['vader_compound']) / 2
                smiley = '😐' if mean_sentiment == 0 else '😊' if mean_sentiment > 0 else '😠'
                hrefs.append(
                    f'<a class="storylink" style="background-color: {bias_colors[a['bias'] + 3]}"'
                    f' href="{a["url"]}">{a["agency"]} {smiley}</a>'
                )
            agency_lists[cluster['cluster']] = ' '.join(hrefs)
        self.context['agency_lists'] = agency_lists

    def summarize(self, df):
        # group each cluster, concatenate the processed text, and summarize with nlp
        summaries = {}
        logger.info("Summarizing all clusters")
        i = 0
        for key, group in df.groupby('cluster'):
            # sort the group by title length
            group['text_length'] = group['title'].str.len()
            group = group.sort_values(by='text_length', ascending=False)

            # Take only full headlines adding up to 1024
            length = 0
            strings = []
            while length < 1024 and not group.empty:
                length += len(group.iloc[0]['title'])
                if length >= 1024:
                    break
                strings.append(group.iloc[0]['title'])
                group = group.iloc[1:]
            mean_char = sum([len(x) for x in strings]) / len(strings)
            mean_tok = mean_char / 2
            text = ' '.join(strings)

            # Estimate the number of tokens by either by whichever is smaller, the mean or 75% of the total length
            # Otherwise summarizer nags about input_length being shorter than max_length
            # You'd think these bastards would give us a way to just count the tokens
            est_tok = round(min(mean_tok, len(text.split()) * 0.9))

            summaries[key] = summarizer(
                ' '.join(strings),
                min_length=int(est_tok / 2),
                max_new_tokens=est_tok,
                do_sample=True,
                early_stopping=True
            )[0]['summary_text']

            i += 1
            logger.info("Summarized cluster %i: %s", i, summaries[key])
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
        df = df[['title', 'first_accessed', 'last_accessed', 'score', 'topic', 'vader_compound', 'afinn']]
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
        return calculate_xkeyscore(df.copy())


if __name__ == '__main__':
    Config.set_debug()
    HeadlinesPage(DataHandler([DataTypes.headlines])).generate()
    copy_assets()
