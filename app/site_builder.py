import os
import shutil
import string
from datetime import datetime as dt, timedelta as td, timezone as tz
from typing import Optional

import nltk
import numpy as np
from wordcloud import WordCloud, STOPWORDS

from app import j2env
from app.config import Config
from app.models import Session, Agency, Article, Headline
from app.logger import get_logger

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


class TimeConstants:
    last_hour = dt.now()
    last_hour = last_hour.replace(hour=last_hour.hour - 1)
    midnight = dt.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = midnight - td(days=1)
    timezone = tz(td(hours=-5))


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

class AgencyPage:
    template = j2env.get_template('agency.html')

    def __init__(self, agency: Agency, s: Session):
        self.agency = agency
        self.s: Session = s

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
            .filter(Article.first_accessed > TimeConstants.yesterday,
                    Article.last_accessed > TimeConstants.midnight,
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
            'wordcloud': f'{self.agency.name}.png',
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
                urls=self.urls
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
                    Headline.first_accessed > TimeConstants.midnight,
                    Headline.last_accessed > TimeConstants.last_hour
                ).all(),
                os.path.join(Config.build, 'wordcloud.png')
            )


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
    copy_assets()
    move_to_public()
