import os
import shutil
import string
from datetime import datetime as dt
from typing import Optional

import nltk
from wordcloud import WordCloud, STOPWORDS

from app import j2env
from app.config import Config
from app.models import Session, Agency, Article
from app.logger import get_logger

logger = get_logger(__name__)

POS = [
    'FW', 'JJ', 'JJR', 'JJS', 'NN', 'NNS', 'NNP', 'NNPS', 'PDT', 'RB',
    'RBR', 'RBS', 'RP', 'UH', 'VB', 'VBD', 'VBG', 'VBN', 'VNP', 'VBZ'
]

STOPWORDS = list(STOPWORDS)
# clean some default words
STOPWORDS.extend(['say', 'said', 'says', "n't", 'Mr', 'Ms', 'Mrs', 'time', 'year', 'week', 'month'])
# strip stray letters
STOPWORDS.extend([l for l in string.ascii_lowercase + string.ascii_uppercase])

midnight = dt.now().replace(hour=0, minute=0, second=0, microsecond=0)


def filter_words(text: str, parts_of_speech: Optional[list[str]] = None):
    if parts_of_speech is None:
        parts_of_speech = POS
    words = filter(lambda word: word[1] in parts_of_speech, nltk.pos_tag(nltk.word_tokenize(text)))
    return ' '.join([word[0] for word in words])


def generate_wordcloud(articles, path):
    # filter for only articles from the last hour
    wc = WordCloud(background_color="white", max_words=2000, width=800, height=400, stopwords=STOPWORDS)
    wc.generate(
        filter_words(
            ' '.join([article.title + ' ' + article.body for article in articles]),
            ['NN', 'NNS', 'NNP', 'NNPS']
        )
    )
    wc.to_file(path)


def generate_agency_pages():
    template = j2env.get_template('agency.html')
    s = Session()
    for agency in s.query(Agency).all():
        vars = {
            'title': agency.name,
            'agency_name': agency.name,
            'wordcloud': f'{agency.name}.png',
            'articles': agency.articles.filter(Article.last_accessed > midnight).order_by(Article.last_accessed.desc()).all(),
            'bias': str(agency.bias),
            'credibility': str(agency.credibility),
            'sentiment': agency.todays_sentiment(s).to_frame().to_html()
        }
        generate_wordcloud(
            vars['articles'],
            os.path.join(Config.build, vars['wordcloud'])
        )
        with open(os.path.join(Config.build, f'{agency.name}.html'), 'wt') as f:
            f.write(template.render(**vars))
            logger.info(f"Generated page for %s", agency.name)
    s.close()


def generate_homepage():
    template = j2env.get_template('index.html')
    with Session() as s:
        agencies = s.query(Agency).all()
        generate_wordcloud(
            s.query(Article).filter(Article.last_accessed > midnight).all(),
            os.path.join(Config.build, 'wordcloud.png')
        )
    with open(os.path.join(Config.build, 'index.html'), 'wt') as f:
        f.write(template.render(title='Home', agencies=agencies))


def copy_assets():
    for file in os.listdir(Config.assets):
        shutil.copy(os.path.join(Config.assets, file), Config.build)

def move_to_public():
    server_location = os.environ['SERVER_LOCATION']
    shutil.move(Config.build, server_location)


def build_site():
    generate_agency_pages()
    generate_homepage()
    copy_assets()
    move_to_public()
