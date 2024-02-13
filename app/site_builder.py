import os
import shutil
import string
from typing import Optional

import nltk
import numpy as np
import pandas as pd
import seaborn as sns
import yaml
from matplotlib import pyplot as plt, dates as mdates
from sqlalchemy import func
from wordcloud import WordCloud, STOPWORDS

from app import j2env
from app.config import Config
from app.constants import Constants
from app.logger import get_logger
from app.models import Session, Agency, Article, Headline

logger = get_logger(__name__)

POS = ['NN', 'NNS', 'NNP', 'NNPS']

STOPWORDS = list(STOPWORDS)
# clean some default words
STOPWORDS.extend([
    'say', 'said', 'says', "n't", 'Mr', 'Ms', 'Mrs', 'time', 'year', 'week', 'month', "years",
    "people", "life", "day", "thing", "something", "number", "system", "video", "months", "group",
    "state", "country", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "home", "effort", "product", "part", "cup", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
    "Oct", "Nov", "Dec", "company", "companies", "business"
])
# strip stray letters
STOPWORDS.extend([l for l in string.ascii_lowercase + string.ascii_uppercase])



def filter_words(text: str, parts_of_speech: Optional[list[str]] = None):
    if parts_of_speech is None:
        parts_of_speech = POS
    words = filter(lambda word: word[1] in parts_of_speech, nltk.pos_tag(nltk.word_tokenize(text)))
    return ' '.join([word[0] for word in words])


def generate_wordcloud(headlines: list[Headline], path: str):
    wc = WordCloud(background_color="white", max_words=100, width=800, height=400, stopwords=STOPWORDS)
    logger.debug("Generating wordcloud for %s articles", len(headlines))
    text = ' '.join([headline.title for headline in headlines])
    logger.debug("There are %d words", text.count(' '))
    if not text.strip():
        logger.warning("No text to generate wordcloud")
        return
    wc.generate(filter_words(text, ['NN', 'NNS', 'NNP', 'NNPS']))
    logger.debug("Saving wordcloud to %s", path)
    wc.to_file(path)

class AgencyHeadlineShiftPages:
    template = j2env.get_template('agency-shift.html')

    def __init__(self, agency: Agency, s: Session):
        self.agency = agency
        self.s: Session = s

    def generate(self):
        articles = self.s.query(Article).filter(Article.agency_id == self.agency.id)\
                    .join(Headline, Article.id == Headline.article_id)\
                    .filter(Headline.first_accessed > Constants.TimeConstants.yesterday,
                            Headline.last_accessed > Constants.TimeConstants.midnight)\
                    .having(func.count(Headline.id) > 5).group_by(Article.id).all()

        for article in articles:
            df = pd.DataFrame([{
                'sentiment': h.headcompound,
                'date': h.first_accessed,
                'title': h.title,
            } for h in article.headlines])
            if df.sentiment.nunique() <= 1:
                continue
            self.generate_plot(df, article)

    @staticmethod
    def generate_plot(df: pd.DataFrame, article: Article):
        sns.lineplot(data=df, x='date', y='sentiment')
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
        plt.xticks(rotation=45)
        plt.title(f"Sentiment Shift for {article.url}")
        plt.tight_layout()
        filename = article.url.replace('/', '_')
        plt.savefig(os.path.join(Config.build, f"{filename}.png"))
        plt.clf()


class AgencyPage:
    template = j2env.get_template('agency.html')

    def __init__(self, agency: Agency, s: Session):
        self.agency = agency
        self.s: Session = s
        self.wordcloud_filename = f'{self.agency.name}.png'

    def generate(self):
        logger.info("Generating page for %s...", self.agency.name)
        variables = self.get_variables()
        if variables['headlines']:
            generate_wordcloud(
                variables['headlines'],
                str(os.path.join(Config.build, variables['wordcloud']))
            )
        with open(os.path.join(Config.build, f'{self.agency.name}.html'), 'wt') as f:
            f.write(self.template.render(**variables))
        logger.info("Done")

    def get_variables(self):
        s = self.s
        headlines = s.query(Headline) \
            .join(Article, Article.id == Headline.article_id) \
            .filter(Article.first_accessed > Constants.TimeConstants.yesterday,
                    Article.last_accessed > Constants.TimeConstants.midnight,
                    Article.agency_id == self.agency.id) \
            .order_by(Headline.last_accessed.desc()).all()
        tabledata = []
        urls = {}
        for headline in headlines:
            urls[headline.title] = headline.article.url
            tabledata.append([
                headline.title,
                headline.article.first_accessed.strftime('%Y-%m-%d %H:%M:%S'),
                headline.article.last_accessed.strftime('%Y-%m-%d %H:%M:%S'),
                headline.headcompound
            ])
        return {
            'agency_name': self.agency.name,
            'headlines': headlines,
            'bias': str(self.agency.bias),
            'credibility': str(self.agency.credibility),
            'tabledata': tabledata,
            'title': self.agency.name,
            'urls': urls,
            'wordcloud': self.wordcloud_filename
        }


def generate_agency_pages():
    s = Session()
    for agency in s.query(Agency).filter(Agency.articles.any()).all():
        AgencyPage(agency, s).generate()
    s.close()


class HomePage:
    template = j2env.get_template('index.html')

    def __init__(self):
        self.data = []
        self.urls = {}
        self.agencies = []
        self.wordcloud_filename = 'wordcloud.png'

    def generate(self):
        logger.info("Generating home page...")
        self.generate_home_wordcloud()
        self.generate_home_data()
        self.render_home_page()
        logger.info("...done")

    def render_home_page(self):
        with open(os.path.join(Config.build, 'index.html'), 'wt') as f:
            f.write(self.template.render(
                title='Home',
                agencies=self.agencies,
                tabledata=self.data,
                urls=self.urls,
                wordcloud=self.wordcloud_filename
            ))

    def generate_home_data(self):
        with Session() as s:
            self.agencies: list[Agency] = s.query(Agency).filter(Agency.articles.any()).order_by(Agency.name).all()
            for agency in self.agencies:
                sentiment = agency.todays_compound()
                sentiment = round(sentiment, 2) if not np.isnan(sentiment) else "N/A"
                self.data.append([agency.name, agency.credibility.value, agency.bias.value, sentiment])
                self.urls[agency.name] = f"{agency.name}.html"

    def generate_home_wordcloud(self):
        with Session() as s:
            generate_wordcloud(
                s.query(Headline).filter(
                    Headline.first_accessed > Constants.TimeConstants.midnight,
                    Headline.last_accessed > Constants.TimeConstants.last_hour
                ).all(),
                os.path.join(Config.build, self.wordcloud_filename)
            )

class Blog:
    page = j2env.get_template('blog.html')
    index = j2env.get_template('blog.index.html')

    def __init__(self):
        self.posts = []

    def generate(self):
        logger.info("Generating blog...")
        self.load_posts()
        self.render_blog_index()
        self.render_blog()
        logger.info("...done")

    def load_posts(self):
        path = os.path.join(Constants.Paths.ROOT, 'app', 'posts')
        for file in os.listdir(path):
            with open(os.path.join(path, file), 'rt') as f:
                frontmatter, post = self.read_frontmatter(f.read())
            url = frontmatter['title'].lower()
            for item in string.punctuation + ' ':
                url = url.replace(item, '-')
            url = url.strip('-') + '.html'

            self.posts.append({
                'title': frontmatter['title'],
                'date': frontmatter['date'],
                'body': post,
                'url': url
            })

    @staticmethod
    def read_frontmatter(post):
        frontmatter = post.split('---')[1]
        post = post.split('---')[2]
        frontmatter: dict = yaml.safe_load(frontmatter)
        return frontmatter, post

    def render_blog_index(self):
        with open(os.path.join(Config.build, 'blog.html'), 'wt') as f:
            f.write(self.index.render(posts=self.posts))

    def render_blog(self):
        for post in self.posts:
            with open(os.path.join(Config.build, post['url']), 'wt') as f:
                f.write(self.page.render(post=post))



def copy_assets():
    for file in os.listdir(Config.assets):
        logger.debug(f"Copying %s", file)
        shutil.copy(os.path.join(Config.assets, file), Config.build)


def move_to_public():
    server_location = os.environ.get('SERVER_LOCATION', None)
    if server_location is None:
        logger.warning("No server location specified, not moving files")
        return

    for file in os.listdir(Config.build):
        logger.debug(f"Moving %s", file)
        shutil.move(os.path.join(Config.build, file), os.path.join(server_location, file))


def build_site():
    generate_agency_pages()
    HomePage().generate()
    Blog().generate()
    copy_assets()
    move_to_public()
