import os
from datetime import datetime as dt, timedelta as td

import pytz

from app.site import j2env
from app.utils import Config, Constants, get_logger, Country
from app.models import Session, Headline

logger = get_logger(__name__)


class HeadlinesPage:
    template = j2env.get_template('headlines.html')

    def generate(self):
        logger.info("Generating headlines page...")
        with Session() as s:
            headlines: list[Headline] = s.query(Headline).filter(
                Headline.last_accessed > Constants.TimeConstants.five_minutes_ago,
                Headline.first_accessed > dt.now() - td(days=1)
            ).order_by(
                Headline.position.asc(),  # prominence
                Headline.first_accessed.desc()
            ).all()
            agency_urls, data, urls = self.get_dicts(headlines)
        with open(os.path.join(Config.build, 'headlines.html'), 'wt') as f:
            f.write(self.template.render(
                title='Headlines',
                tabledata=data,
                urls=urls,
                agencyurls=agency_urls
            ))
        logger.info("...done")

    def get_dicts(self, headlines):
        data = []
        urls = {}
        agency_urls = {}
        for h in headlines:
            if h.article.agency.country not in [Country.us, Country.gb]:
                continue
            if h.article.agency.country == Country.gb and h.article.agency.name not in [
                "The Economist",
                "BBC",
                "The Guardian",
            ]:
                continue
            data.append([
                h.title,
                h.article.agency.name,
                h.first_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone) \
                    .strftime('%b %-d %-I:%M %p'),
                h.last_accessed.replace(tzinfo=pytz.UTC).astimezone(tz=Constants.TimeConstants.timezone) \
                    .strftime('%-I:%M %p'),
                h.position,
                h.vader_compound,
                h.afinn
            ])
            urls[h.title] = h.article.url
            agency_urls[h.article.agency.name] = h.article.agency.url
        return agency_urls, data, urls
