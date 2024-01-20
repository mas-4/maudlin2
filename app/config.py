import os
import pathlib

class Config:
    use_color = True
    root = pathlib.Path(__file__).parent.parent.absolute()
    output_dir = os.path.join(root, 'data')
    log_file = f'{output_dir}/app.log'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    logging_level = 'DEBUG'

    connection_string = f'sqlite:///{output_dir}/data.db'

    @staticmethod
    def time_between_requests() -> float:  # this is a function so we can make it random if necessary
        return 2
