import os

class Config:
    use_color = True
    log_file = 'logs/scraper.log'
    if not os.path.exists('logs'):
        os.makedirs('logs')
    logging_level = 'DEBUG'

    @staticmethod
    def time_between_requests():
        return 2
