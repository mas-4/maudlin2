"""The methods log on the site: docs/methods-log.md as a page, so every change to how bignews.day collects or
measures things (and every mistake and its fix) is public and dated, for anyone reading the numbers or using the
data. Rendered from the same file the repository keeps, so the two never differ."""
import os
import re

import mistune

from app.site.common import TemplateHandler
from app.utils import Constants, get_logger

logger = get_logger(__name__)

LOG = os.path.join(Constants.Paths.ROOT, 'docs', 'methods-log.md')


class MethodsPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('methods.html')

    def generate(self):
        logger.info("Generating methods page...")
        with open(LOG) as f:
            text = f.read()
        # The file's own title and opening paragraph are the page's: the page writes its own
        body = re.sub(r'\A# .*?\n\n.*?\n\n', '', text, count=1, flags=re.S)
        html = mistune.html(body)
        # Each dated section gets an anchor (#2026-10-05) for linking to a day
        html = re.sub(r'<h2>(\d{4}-\d{2}-\d{2})</h2>', r'<h2 id="\1">\1</h2>', html)
        days = re.findall(r'^## (\d{4}-\d{2}-\d{2})', text, flags=re.M)
        self.template.write({'title': 'Methods log', 'log': html, 'days': days})
        logger.info("...%d dated sections", len(days))
