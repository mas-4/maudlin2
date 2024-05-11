from app.site.common import copy_assets, TemplateHandler, PathHandler
from app.site.data import DataHandler, DataTypes
from app.site.wordcloudgen import generate_wordcloud
from app.utils import Config, Bias, Credibility, get_logger

logger = get_logger(__name__)


class AgenciesPage:
    def __init__(self, data: DataHandler):
        self.template = TemplateHandler('agencies.html')
        tabledata = data.agency_data.values.tolist()
        tabledata.sort(key=lambda x: x[-1])
        self.context = {
            'title': 'Agencies',
            'bias': {str(b): b.value for b in list(Bias)},
            'credibility': {str(c): c.value for c in list(Credibility)},
            'tabledata': tabledata,
            'metrics': data.agency_metrics
        }
        self.data: DataHandler = data

    def generate(self):
        logger.info("Generating agencies page...")
        logger.info("Generating current headlines wordcloud...")
        generate_wordcloud(self.data.current_processed_headlines,
                           PathHandler(PathHandler.FileNames.main_wordcloud).build)
        self.template.write(self.context)
        logger.info("...done")


if __name__ == "__main__":
    Config.set_debug()
    copy_assets()
    dh: DataHandler = DataHandler([DataTypes.agency])
    AgenciesPage(dh).generate()
