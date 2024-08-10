from app.site.common import TemplateHandler
from app.site.data import DataHandler
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PollingPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.context = {'title': 'Polling'}
        self.template = TemplateHandler('polling.html')

    def generate(self):
        self.template.write(self.context)
