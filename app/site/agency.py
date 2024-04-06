import os
from datetime import timedelta as td

import pandas as pd
import pytz

from app.models import Agency, Session, Headline, Article
from app.registry import Scrapers
from app.site import j2env
from app.site.common import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


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
                [h.processed for h in variables['headlines']],
                str(os.path.join(Config.build, variables['wordcloud']))
            )
        with open(os.path.join(Config.build, f'{self.agency.name}.html'), 'wt') as f:
            f.write(self.template.render(**variables))
        df = pd.DataFrame(variables['tabledata'], columns=['Title', 'First Accessed', '# Headlines', 'Vader', 'Afinn'])
        df['url'] = df['Title'].map(variables['urls'])
        df.to_csv(os.path.join(Config.build, f'{self.agency.name}.csv'), index=False)
        logger.info("Done")

    def get_variables(self):
        s = self.s
        agency_filter = Article.agency_id == self.agency.id
        first_accessed_filter = Article.first_accessed > s.query(Article.first_accessed).filter(agency_filter).order_by(
            Article.first_accessed.asc()
        ).first()[0] + td(days=1)  # To filter out permanent links
        base_query = s.query(Headline).join(Article, Article.id == Headline.article_id) \
            .order_by(Headline.last_accessed.desc()).filter(first_accessed_filter, agency_filter)
        if Config.debug:
            headlines = base_query.limit(10).all()
        else:
            headlines = base_query.filter(Article.last_accessed > Config.last_accessed).all()
        tabledata = []
        urls = {}
        for headline in headlines:
            # I don't remember why this is necessary, but I'll leave it for now because it should help - M 2024-04-06
            if not Config.debug and headline.last_accessed < Config.last_accessed:
                continue
            urls[headline.processed] = headline.article.url
            strftime = '%b %-d %-I:%M %p'
            tabledata.append([
                headline.processed,
                headline.first_accessed.replace(tzinfo=pytz.UTC).astimezone(
                    tz=Constants.TimeConstants.timezone).strftime(strftime),
                len(headline.article.headlines),
                round(headline.vader_compound, 2),
                round(headline.afinn, 2)
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
    agencies = [scraper.agency for scraper in Scrapers]
    for agency in s.query(Agency).filter(Agency.articles.any()).all():
        if agency.name in agencies:
            AgencyPage(agency, s).generate()
    s.close()
