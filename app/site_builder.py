import os
import shutil
import string
from datetime import datetime as dt, timedelta
from typing import Optional

import nltk
from wordcloud import WordCloud, STOPWORDS

from app import j2env
from app.config import Config
from app.models import Session, Agency

POS = [
    'FW', 'JJ', 'JJR', 'JJS', 'NN', 'NNS', 'NNP', 'NNPS', 'PDT', 'RB',
    'RBR', 'RBS', 'RP', 'UH', 'VB', 'VBD', 'VBG', 'VBN', 'VNP', 'VBZ'
]

STOPWORDS = list(STOPWORDS)
# clean some default words
STOPWORDS.extend(['say', 'said', 'says', "n't", 'Mr', 'Ms', 'Mrs', 'time', 'year', 'week', 'month'])
# strip stray letters
STOPWORDS.extend([l for l in string.ascii_lowercase + string.ascii_uppercase])


def filter_words(text: str, parts_of_speech: Optional[list[str]] = None):
    if parts_of_speech is None:
        parts_of_speech = POS
    tokenized = nltk.pos_tag(nltk.word_tokenize(text))
    words = filter(lambda word: word[1] in parts_of_speech, tokenized)
    return ' '.join([word[0] for word in words])


def generate_wordcloud(agency, path):
    # filter for only articles from the last hour
    articles = filter(lambda article: article.last_accessed > dt.now() - timedelta(hours=1), agency.articles)
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
    with Session() as s:
        for agency in s.query(Agency).all():
            wordcloud_name = f'{agency.name}.png'
            with open(os.path.join(Config.build, f'{agency.name}.html'), 'wt') as f:
                f.write(template.render(title=agency.name, agency=agency, wordcloud=wordcloud_name))
            generate_wordcloud(agency, os.path.join(Config.build, wordcloud_name))


def copy_assets():
    for file in os.listdir(Config.assets):
        shutil.copy(os.path.join(Config.assets, file), Config.build)

def build_site():
    generate_agency_pages()
    copy_assets()

