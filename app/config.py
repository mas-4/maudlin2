import os

class Config:
    use_color = True
    output_dir = 'data'
    log_file = f'{output_dir}/app.log'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    logging_level = 'DEBUG'

    connection_string = f'sqlite:///{output_dir}/data.db'

    @staticmethod
    def time_between_requests() -> float:  # this is a function so we can make it random if necessary
        return 2
