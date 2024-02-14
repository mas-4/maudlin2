import os

from app import j2env
from app.config import Config
from app.constants import Constants
from app.logger import get_logger
from app.models import Agency, Session, Headline, Article
from app.site.common import generate_wordcloud

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
            .filter(Article.first_accessed > Constants.TimeConstants.yesterday,
                    Article.last_accessed > Constants.TimeConstants.midnight,
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
            'wordcloud': self.wordcloud_filename
        }


def generate_agency_pages():
    s = Session()
    for agency in s.query(Agency).filter(Agency.articles.any()).all():
        AgencyPage(agency, s).generate()
    s.close()
