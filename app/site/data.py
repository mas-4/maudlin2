from app.models import Session, Headline, Article, Agency
import pandas as pd


class DataHandler:
    def __init__(self):
        self.all_sentiment_data = self.aggregate_sentiment_data()

    @staticmethod
    def aggregate_sentiment_data():
        with Session() as s:
            data = s.query(
                Headline.vader_compound, Headline.afinn, Headline.last_accessed, Agency._bias  # noqa protected
            ).join(Headline.article).join(Article.agency).all()
        df = pd.DataFrame(data, columns=['Vader', 'Afinn', 'Date', 'Bias'])
        df['Date'] = pd.to_datetime(df['Date'])
        df['PVI'] = df['Vader'] * df['Bias']
        df['PAI'] = df['Afinn'] * df['Bias']
        cols = ['Vader', 'Afinn', 'PVI', 'PAI']
        agg = df.set_index('Date').groupby(pd.Grouper(freq='D')) \
            .agg({col: 'mean' for col in cols}).dropna().reset_index()
        # moving averages for vader and afinn
        agg['Vader MA'] = agg['Vader'].rolling(window=7).mean()
        agg['Afinn MA'] = agg['Afinn'].rolling(window=7).mean()
        agg['PVI MA'] = agg['PVI'].rolling(window=7).mean()
        agg['PAI MA'] = agg['PAI'].rolling(window=7).mean()
        return agg
