"""The About page (Oct 27, before the site goes on Bluesky and Mastodon): what the site is, in a minute's read, for
someone who arrives from a shared link. Who makes it, how, what it won't do, how to reach us. The details live on
How it works (glossary) and the Methods log."""
from app.site.common import TemplateHandler
from app.utils import get_logger

logger = get_logger(__name__)

# How to reach us, shown on the page once the person picks one (an address, a Bluesky handle); empty hides the line
CONTACT = ''


class AboutPage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('about.html')

    def generate(self):
        logger.info("Generating about page...")
        from app.vernacular import RETENTION_DAYS
        self.template.write({'title': 'About', 'contact': CONTACT, 'retention': RETENTION_DAYS,
                             'og_description': "What bignews.day is: the news and the stories told about it, "
                                               "read the way a folklorist reads tales, left and right alike."})
