import os
from random import random
import pathlib
from app import j2env

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


def date(value):
    return value.strftime(Config.strf)

j2env.globals['Config'] = Config
j2env.filters['date'] = date