import os

class Config:
    use_color = True
    log_file = 'logs/scraper.log'
    if not os.path.exists('logs'):
        os.makedirs('logs')
    logging_level = 'DEBUG'

    connection_string = 'sqlite:///data.db'

    @staticmethod
    def time_between_requests():
        return 2
