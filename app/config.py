import os
import pathlib
from random import random

from app import j2env
from app.constants import Constants


class Config:
    use_color = True
    logging_level = 'DEBUG'
    site_name = 'Maudlin'
    strf = '%Y-%m-%d %H:%M:%S'
    dev_mode = False

    root = pathlib.Path(__file__).parent.parent.absolute()
    output_dir = os.path.join(root, 'data')
    log_file = f'{output_dir}/app.log'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    assets = os.path.join(root, 'app', 'static')
    build = os.path.join(root, 'build')
    if not os.path.exists(build):
        os.makedirs(build)

    connection_string = f'sqlite:///{output_dir}/data.db'

    @staticmethod
    def time_between_requests() -> float:  # this is a function so that we can make it random if necessary
        return random() * 2 + 2

    emails = []
    email = ''
    pw = ''
    domain = ''

    if os.path.exists(Constants.Paths.EMAIL_CREDS):
        with open(Constants.Paths.EMAIL_CREDS, 'rt') as f_in:
            emails, domain, email, pw = f_in.readlines()
            emails_to_notify = emails.split(',')


# <editor-fold desc="Jinja2 Environment Stuff">
j2env.globals['Config'] = Config

def date(value):
    return value.strftime(Config.strf)


j2env.filters['date'] = date
# </editor-fold>