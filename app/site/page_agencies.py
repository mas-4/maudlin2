import numpy as np
import pandas as pd

from app.models import Session, Agency, Headline
from app.registry import SeleniumScrapers, TradScrapers
from app.site.common import copy_assets, TemplateHandler, PathHandler
from app.site.data import DataHandler
from app.site.wordcloudgen import generate_wordcloud
from app.utils.config import Config
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AgenciesPage:
    def __init__(self, data: DataHandler):
        self.urls = {}
        self.agencies = []
        self.template = TemplateHandler('agencies.html')
        self.context = {
            'title': 'Agencies',
            'bias': {str(b): b.value for b in list(Bias)},
            'credibility': {str(c): c.value for c in list(Credibility)}
        }
        self.data: DataHandler = data

    def generate(self):
        logger.info("Generating agencies page...")
        self.generate_home_wordcloud()
        self.tabledata()
        self.render_home_page()
        logger.info("...done")

    def render_home_page(self):
        self.context.update({'urls': self.urls})
        self.template.write(self.context)

    def tabledata(self):
        with Session() as s:
            scrapers = TradScrapers
            if Config.run_selenium:
                scrapers += SeleniumScrapers
            self.agencies: list[Agency] = s.query(Agency).filter(
                Agency.articles.any(),
                Agency.name.in_([x.agency for x in scrapers])
            ).order_by(Agency.name).all()
            self.context['tabledata'] = []
            for agency in self.agencies:
                if np.isnan(vader := round(agency.current_vader(), 2)):
                    logger.warning("Vader is na for %r.", agency)
                    continue
                if np.isnan(afinn := round(agency.current_afinn(), 2)):
                    logger.warning("Afinn is na for %r.", agency)
                    continue
                self.context['tabledata'].append(
                    [agency.name, str(agency.credibility), str(agency.bias), str(agency.country),
                     round(agency.todays_churn(s), 2), vader, afinn]
                )
                self.urls[agency.name] = f"{agency.name}.html"
        self.context['tabledata'].sort(key=lambda x: x[-1])
        df = pd.DataFrame(self.context['tabledata'],
                          columns=['Agency', 'Credibility', 'Bias', 'Country', 'Churn', 'Vader', 'Afinn'])
        df['Bias'] = df['Bias'].map({str(b): b.value for b in list(Bias)})
        df['Credibility'] = df['Credibility'].map({str(c): c.value for c in list(Credibility)})
        us = df[df['Country'] == "United States"]
        self.context['metrics'] = {'median_vader': us['Vader'].median(), 'mean_vader': us['Vader'].mean(),
                                   'partisan_mean_vader': (us['Bias'] * us['Vader']).mean(),
                                   'median_afinn': us['Afinn'].median(),
                                   'mean_afinn': us['Afinn'].mean(),
                                   'partisan_mean_afinn': (us['Bias'] * us['Afinn']).mean()}

    @staticmethod
    def generate_home_wordcloud():
        logger.info("Generating current headlines wordcloud...")
        with Session() as s:
            titles = s.query(Headline.processed).filter(
                Headline.last_accessed > Config.last_accessed
            ).all()
            generate_wordcloud(titles, PathHandler(PathHandler.FileNames.main_wordcloud).build)


if __name__ == "__main__":
    Config.set_debug()
    copy_assets()
    dh: DataHandler = DataHandler()
    AgenciesPage(dh).generate()
