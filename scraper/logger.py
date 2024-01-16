"""
This module defines several functions for our logging system.

To add logging to a file:

```
from common import get_logger
logger = get_logger(__name__)
```

If the file you're adding logging to is in `common`:

```
from common.logger import get_logger
logger = get_logger(__name__)
```

It just makes imports simpler in the long run.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from config import Config

class Colors:
    """
    Class for defining colors for the logger
    """
    reset = "\u001b[0m"
    bold_red = "\u001b[31;1m"
    red = "\u001b[31m"
    bold_green = "\u001b[32;1m"
    green = "\u001b[32m"
    bold_yellow = "\u001b[33;1m"
    yellow = "\u001b[33m"
    bold_blue = "\u001b[34;1m"
    blue = "\u001b[34m"
    bold_magenta = "\u001b[35;1m"
    magenta = "\u001b[35m"
    bold_cyan = "\u001b[36;1m"
    cyan = "\u001b[36m"
    bold_white = "\u001b[37;1m"
    white = "\u001b[37m"
    grey = "\u001b[90m"
    bold_grey = "\u001b[90;1m"


class StreamFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG: Colors.blue,
        logging.INFO: Colors.grey,
        logging.WARNING: Colors.yellow,
        logging.ERROR: Colors.red,
        logging.CRITICAL: Colors.bold_red,
    }
    OPENER = "[%(asctime)s:%(levelname)8s] "
    CLOSER = " (%(filename)s:%(lineno)d)"

    def __init__(self, use_color=True):
        super().__init__()
        self.use_color = use_color and Config.use_color

    def format(self, record):
        if self.use_color and record.levelno in self.FORMATS:
            return logging.Formatter(
                ''.join([self.OPENER, self.FORMATS.get(record.levelno), "%(message)s", Colors.reset, self.CLOSER])
            ).format(record)
        else:
            return logging.Formatter(''.join([self.OPENER, "%(message)s", self.CLOSER])).format(record)


def _get_file_handler() -> RotatingFileHandler:
    """
    Internal function for generating a file handler

    Returns
    -------
    RotatingFileHandler
    """
    # we keep it infinite because otherwise in some pipelines it errors
    file_handler = RotatingFileHandler(Config.log_file)
    file_handler.setFormatter(StreamFormatter(False))
    return file_handler


def _get_console_handler() -> logging.StreamHandler:
    """
    Internal function for generating a streamhandler.

    Returns
    -------
    StreamHandler
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StreamFormatter())
    return console_handler


def get_logger(logger_name: str) -> logging.Logger:
    """
    Wrapper for getting a logger. Call like so

    logger = get_logger(__name__)

    Parameters
    ----------
    logger_name: str
        Just pass __name__

    Returns
    -------
    Logger
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(Config.logging_level)
    logger.addHandler(_get_file_handler())
    logger.addHandler(_get_console_handler())
    logger.propagate = False
    return logger