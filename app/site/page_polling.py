from app.polling import Polling, WINDOW_DAYS, RACE_WINDOW_DAYS
from app.site.common import TemplateHandler
from app.site.data import DataHandler
from app.site.graphing import Plots
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PollingPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.context = {'title': 'Polling', 'window_days': WINDOW_DAYS, 'race_window_days': RACE_WINDOW_DAYS}
        self.template = TemplateHandler('polling.html')

    def generate(self):
        polling = Polling()
        if polling.available:
            if polling.chart_generic:
                Plots.generic_ballot(polling.generic)
            if polling.chart_approval:
                Plots.approval(polling.approval)
        self.context['polling'] = polling
        self.template.write(self.context)
