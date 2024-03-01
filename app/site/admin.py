import pandas as pd
from flask import Flask
from app.models import Session, Headline, Article, Agency
from app.utils import Constants

app = Flask(__name__)

@app.route('/')
def home():
    with Session() as s:
        headlines = s.query(
            Headline.title, Article.url, Agency.name
        ).join(Headline.article).join(Article.agency).filter(
            Headline.last_accessed >= Constants.TimeConstants.midnight,
            Headline.first_accessed >= Constants.TimeConstants.yesterday
        ).all()
    df = pd.DataFrame(headlines, columns=['Title', 'URL', 'Agency'])


if __name__ == '__main__':
    app.run(debug=True)
