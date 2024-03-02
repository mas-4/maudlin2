import cachetools.func
import pandas as pd
from flask import Flask

from app.models import Session
from app.queries import Queries
from app.site import j2env
from app.site.common import calculate_xkeyscore

app = Flask(__name__)


@cachetools.func.ttl_cache(maxsize=1, ttl=60 * 10)
def get_data():
    with Session() as s:
        dfdata = [[a.id,
                   a.most_recent_headline().title,
                   a.url,
                   a.agency.name,
                   a.first_accessed.strftime('%b %-d %-I:%M %p'),
                   a.last_accessed.strftime('%-I:%M %p'),
                   a.most_recent_headline().position] for a in Queries.get_todays_articles(s).all()]
    df = pd.DataFrame(dfdata, columns=['id', 'title', 'url', 'agency', 'first_accessed', 'last_accessed', 'index'])
    urls = df.set_index('title')['url'].to_dict()
    df['title'] = df['agency'] + ': ' + df['title']
    calculate_xkeyscore(df)
    df = df[['id', 'title', 'first_accessed', 'last_accessed', 'index', 'score']]
    return df, urls


@app.route('/')
def home():
    print("Called")
    df, urls = get_data()
    return j2env.get_template('headlines-admin.html').render(
        title="Headlines Admin",
        tabledata=df.values.tolist(),
        urls=urls,
    )


if __name__ == '__main__':
    app.run(debug=True)
