import os

import pytz

from app.site import j2env
from app.utils import Config, Constants, get_logger
from app.models import Session, Headline

logger = get_logger(__name__)


class HeadlinesPage:
    template = j2env.get_template('headlines.html')

    def generate(self):
        logger.info("Generating headlines page...")
        with Session() as s:
            headlines: list[Headline] = s.query(Headline) \
                .filter(Headline.last_accessed > Constants.TimeConstants.midnight,
                        Headline.first_accessed > Config.first_accessed) \
                .order_by(Headline.first_accessed.desc(),
                          Headline.last_accessed.desc()) \
                .all()
            data = []
            urls = {}
            agency_urls = {}
            for h in headlines:
                data.append([
                    h.title,
                    h.article.agency.name,
                    h.first_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone) \
                        .strftime('%b %-d %-I:%M %p'),
                    h.last_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone) \
                        .strftime('%-I:%M %p'),
                    h.comp,
                ])
                urls[h.title] = h.article.url
                agency_urls[h.article.agency.name] = h.article.agency.url
        with open(os.path.join(Config.build, 'headlines.html'), 'wt') as f:
            f.write(self.template.render(
                title='Headlines',
                tabledata=data,
                urls=urls,
                agencyurls=agency_urls
            ))
        logger.info("...done")
