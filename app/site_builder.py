import os
import shutil
import string
from datetime import datetime as dt
from typing import Optional

import nltk
import numpy as np
from wordcloud import WordCloud, STOPWORDS

from app import j2env
from app.config import Config
from app.constants import Bias, Credibility
from app.models import Session, Agency, Article
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

midnight = dt.now().replace(hour=0, minute=0, second=0, microsecond=0)


def get_navbar():
    return j2env.get_template('nav.html').render()

def get_footer():
    return j2env.get_template('footer.html').render(now=dt.now().strftime('%m-%d-%Y %H:%M:%S'))


def filter_words(text: str, parts_of_speech: Optional[list[str]] = None):
    if parts_of_speech is None:
        parts_of_speech = POS
    words = filter(lambda word: word[1] in parts_of_speech, nltk.pos_tag(nltk.word_tokenize(text)))
    return ' '.join([word[0] for word in words])


def generate_wordcloud(articles: list[Article], path: str):
    wc = WordCloud(background_color="white", max_words=100, width=800, height=400, stopwords=STOPWORDS)
    logger.info("Generating wordcloud for %s articles", len(articles))
    text = ' '.join([str(article) for article in articles])
    logger.info("There are %d words", text.count(' '))
    wc.generate(filter_words(text, ['NN', 'NNS', 'NNP', 'NNPS'] ))
    logger.info("Saving wordcloud to %s", path)
    wc.to_file(path)


def generate_agency_pages():
    template = j2env.get_template('agency.html')
    s = Session()
    for agency in s.query(Agency).filter(Agency.articles.any()).all():
        logger.info("Generating page for %s...", agency.name)
        variables = get_variables(agency)
        generate_wordcloud(
            variables['articles'],
            str(os.path.join(Config.build, variables['wordcloud']))
        )
        with open(os.path.join(Config.build, f'{agency.name}.html'), 'wt') as f:
            f.write(template.render(**variables))
        logger.info("Done")
    s.close()


def get_variables(agency):
    articles = agency.articles\
        .filter(Article.last_accessed > midnight, Article.failure == False)\
        .order_by(Article.last_accessed.desc()).all()
    tabledata = []
    urls = {}
    for article in articles:
        urls[article.title] = article.url
        tabledata.append([
            article.title,
            article.first_accessed.strftime('%Y-%m-%d %H:%M:%S'),
            article.last_accessed.strftime('%Y-%m-%d %H:%M:%S'),
            article.headcompound,
            article.artcompound or "N/A"
        ])
    return {
        'agency_name': agency.name,
        'articles': articles,
        'bias': str(agency.bias),
        'credibility': str(agency.credibility),
        'headline_only': agency.headline_only,
        'nav': get_navbar(),
        'footer': get_footer(),
        'tabledata': tabledata,
        'title': agency.name,
        'urls': urls,
        'wordcloud': f'{agency.name}.png',
    }


def generate_homepage():
    logger.info(f"Generating homepage")
    template = j2env.get_template('index.html')
    with Session() as s:
        agencies = s.query(Agency).filter(Agency.articles.any()).order_by(Agency.name).all()
        last_hour = dt.now()
        last_hour.replace(hour=last_hour.hour - 1)
        generate_wordcloud(
            s.query(Article).filter(Article.last_accessed > last_hour, Article.failure == False).all(),
            os.path.join(Config.build, 'wordcloud.png')
        )
        data = []
        urls = {}
        for agency in agencies:
            headline, article = agency.todays_compound()
            headline = round(headline, 2) if not np.isnan(headline) else "N/A"
            article = round(article, 2) if not np.isnan(article) else "N/A"
            data.append([agency.name, agency.credibility.value, agency.bias.value, headline, article])
            urls[agency.name] = f"{agency.name}.html"

    with open(os.path.join(Config.build, 'index.html'), 'wt') as f:
        f.write(template.render(
            title='Home',
            agencies=agencies,
            nav=get_navbar(),
            footer=get_footer(),
            tabledata=data,
            bias=Bias.to_dict(),
            credibility=Credibility.to_dict(),
            urls=urls
        ))
    logger.info(f"Generated homepage")


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
    generate_homepage()
    copy_assets()
    move_to_public()
