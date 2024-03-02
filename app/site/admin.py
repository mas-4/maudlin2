import cachetools.func
import pandas as pd
from flask import Flask

from app.models import Session, Headline, Article, Agency
from app.site import j2env
from app.site.common import calculate_xkeyscore
from app.utils.constants import Constants

app = Flask(__name__)


@app.route('/')
def home():
    print("Called")
    df, urls = get_data()
    return j2env.get_template('headlines-admin.html').render(
        title="Headlines Admin",
        tabledata=df.values.tolist(),
        urls=urls,
    )


@cachetools.func.ttl_cache(maxsize=1, ttl=60 * 10)
def get_data():
    columns = {
        'id': Article.id,
        'title': Headline.title,
        'url': Article.url,
        'agency': Agency.name,
        'first_accessed': Article.first_accessed,
        'last_accessed': Article.last_accessed,
        'index': Headline.position
    }
    with Session() as s:
        headlines = s.query(*list(columns.values())).join(Headline.article).join(Article.agency).filter(
            Headline.last_accessed >= Constants.TimeConstants.midnight,
            Headline.first_accessed >= Constants.TimeConstants.yesterday
        ).all()
    df = pd.DataFrame(headlines, columns=list(columns.keys()))
    urls = df.set_index('title')['url'].to_dict()
    df['title'] = df['agency'] + ': ' + df['title']
    df['first_accessed'] = df['first_accessed'].dt.strftime('%b %-d %-I:%M %p')
    df['last_accessed'] = df['last_accessed'].dt.strftime('%-I:%M %p')
    calculate_xkeyscore(df)
    df = df[['id', 'title', 'first_accessed', 'last_accessed', 'index', 'score']]
    return df, urls


if __name__ == '__main__':
    app.run(debug=True)
