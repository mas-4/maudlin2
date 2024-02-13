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
from app.constants import Bias, Credibility
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


def get_navbar():
    return j2env.get_template('nav.html').render()


def get_footer():
    return j2env.get_template('footer.html').render(now=dt.now(TimeConstants.timezone).strftime('%m-%d-%Y %H:%M:%S'))


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


def generate_agency_pages():
    template = j2env.get_template('agency.html')
    s = Session()
    for agency in s.query(Agency).filter(Agency.articles.any()).all():
        logger.info("Generating page for %s...", agency.name)
        variables = get_variables(agency, s)
        if variables['headlines']:
            generate_wordcloud(
                variables['headlines'],
                str(os.path.join(Config.build, variables['wordcloud']))
            )
        with open(os.path.join(Config.build, f'{agency.name}.html'), 'wt') as f:
            f.write(template.render(**variables))
        logger.info("Done")
    s.close()


def get_variables(agency, s):
    headlines = s.query(Headline) \
        .join(Article, Article.id == Headline.article_id) \
        .filter(Article.first_accessed > TimeConstants.yesterday,
                Article.last_accessed > TimeConstants.midnight,
                Article.agency_id == agency.id) \
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
        'agency_name': agency.name,
        'headlines': headlines,
        'bias': str(agency.bias),
        'credibility': str(agency.credibility),
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
        generate_wordcloud(
            s.query(Headline).filter(
                Headline.first_accessed > TimeConstants.midnight,
                Headline.last_accessed > TimeConstants.last_hour
            ).all(),
            os.path.join(Config.build, 'wordcloud.png')
        )
        data = []
        urls = {}
        agencies: list[Agency] = s.query(Agency).filter(Agency.articles.any()).order_by(Agency.name).all()
        for agency in agencies:
            sentiment = agency.todays_compound()
            sentiment = round(sentiment, 2) if not np.isnan(sentiment) else "N/A"
            data.append([agency.name, agency.credibility.value, agency.bias.value, sentiment])
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
