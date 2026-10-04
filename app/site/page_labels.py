"""The loaded labels page: contested vocabulary by side (app/analysis/epithets.py)."""
from app.analysis import epithets
from app.site.common import TemplateHandler
from app.site.data import DataHandler
from app.utils import get_logger

logger = get_logger(__name__)


class LabelsPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('labels.html')
        self.context = {'title': 'Loaded labels'}

    def generate(self):
        logger.info("Generating loaded labels page...")
        self.context.update(epithets.build())
        self.template.write(self.context)
        logger.info("...done")
