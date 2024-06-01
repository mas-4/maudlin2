import os
from datetime import datetime as dt

from app.analysis.clustering import prepare_cosine, form_clusters, label_clusters
from app.analysis.newsiness import get_newsiness
from app.analysis.pipelines import Pipelines, prepare, trem, tnorm
from app.site.common import calculate_xkeyscore, copy_assets, TemplateHandler
from app.site.data import DataHandler, DataTypes
from app.site.graphing import bias_colors
from app.utils import Config, Country, get_logger

logger = get_logger(__name__)

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
        self.analyze_newsiness(self.dh.main_headline_df.copy())
        self.cluster_and_summarize(df.copy())
        table_df = self.process_headlines(df)
        # drop all rows with nan
        table_df.dropna(inplace=True)
        self.context['tabledata'] = table_df.values.tolist()
        self.newsletter.write(self.context)
        self.template.write(self.context)
        logger.info("...done")

    def analyze_newsiness(self, df):
        # Filter df for us or exempted foreign media
        df = df[(df['country'] == Country.us.value) | (df['agency'].isin(Config.exempted_foreign_media))]
        newsiness = get_newsiness(df['title'].tolist())
        # Floor the current time to the previous half hour
        halfhour = dt.now().replace(minute=30 if dt.now().minute >= 30 else 0, second=0, microsecond=0)
        halfhour = halfhour.hour * 60 + halfhour.minute
        weekday = dt.today().strftime("%A")
        ndf = self.dh.newsiness_df
        condition = (ndf['halfhour'] == halfhour) & (ndf['day'] == weekday)
        try:
            std = ndf[condition]['std'].values[0]
            mean = ndf[condition]['mean'].values[0]
            zscore = (newsiness - mean) / std

            if zscore > 1:
                slowday = f'<h1 class="busy newsday">🚨🗞️🚨 BIG NEWS DAY! 🚨🗞️🚨</h1>'
            elif zscore < -1:
                slowday = f'<h1 class="slow newsday">🌴🐢🍹 slow news day... 🍹🐢🌴</h1>'
            else:
                slowday = f'<h1 class="average newsday">📰🥸📰 Just Another Day of News. 📰🥸📰</h1>'
            slowday += f'<h3 style="text-align: center;">Newsiness score: {newsiness:.2f} (z-score: {zscore:.2f})</h3>'
        except IndexError:
            logger.warning("IndexError in analyze_newsiness, hour %i weekday %s", halfhour, weekday)
            slowday = '<h1 class="newsday">No idea how busy today is in the news. 🤷🤷🤷 (system error 🤖🔥🤖)</h1>'

        self.context['slowday'] = slowday

    def cluster_and_summarize(self, df):
        n_samples_per_cluster = 6
        threshold = 0.5
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

        logger.info("Clustering %i headlines", len(df))
        clusters = form_clusters(prepare_cosine(df['processed']), n_samples_per_cluster, threshold)
        logger.info("%i clusters formed", len(clusters))

        df = label_clusters(df, clusters)
        df = df[df['cluster'] != -1].copy()
        df.drop_duplicates(subset=['cluster', 'agency'], keep='first', inplace=True)
        df['text_length'] = df['title'].str.len()
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
            hrefs = [f'<p>{len(cluster['data'])} headlines</p>']
            last_bias = -3
            for a in sorted(cluster['data'], key=lambda x: x['bias']):
                if a['bias'] != last_bias:
                    hrefs.append(f'<br>')
                    last_bias = a['bias']
                mean_sentiment = (a['afinn'] + a['vader_compound']) / 2
                smiley = '😐' if mean_sentiment == 0 else '😊' if mean_sentiment > 0 else '😠'
                bias = a['bias'] + 3
                hrefs.append(
                    f'<a class="storylink" style="background-color: {bias_colors[bias]}" title="{a["title"]}"'
                    f' href="{a["url"]}">{a["agency"]} {smiley}</a>'
                )
            agency_lists[cluster['cluster']] = ' '.join(hrefs)
        self.context['agency_lists'] = agency_lists

    def summarize(self, df):
        # Pick the most center headline from each cluster
        summaries = {}
        for key, group in df.groupby('cluster'):
            group['bias_abs'] = group['bias'].abs()
            # Pick the most center headline and use it as the summary
            center = group.loc[group['bias_abs'].idxmin()]
            summaries[key] = f'{center['agency']}: {center['title']}'
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
