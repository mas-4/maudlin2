import os
import pathlib
from app import j2env

class Config:
    use_color = True

    root = pathlib.Path(__file__).parent.parent.absolute()
    output_dir = os.path.join(root, 'data')
    log_file = f'{output_dir}/app.log'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    assets = os.path.join(root, 'app', 'assets')
    build = os.path.join(root, 'build')
    if not os.path.exists(build):
        os.makedirs(build)

    logging_level = 'DEBUG'
    site_name = 'Maudlin'

    connection_string = f'sqlite:///{output_dir}/data.db'

    @staticmethod
    def time_between_requests() -> float:  # this is a function so we can make it random if necessary
        return 2

j2env.globals['Config'] = Config