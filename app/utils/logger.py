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
import os
import sys
from logging.handlers import RotatingFileHandler

from app.utils.config import Config


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
    CLOSER = " (%(filename)s:%(lineno)d)"

    def __init__(self, use_color=True, timestamp=True):
        super().__init__()
        self.use_color = use_color and Config.use_color
        self.opener = "[%(asctime)s:%(levelname)8s] " if timestamp else "[%(levelname)8s] "

    def format(self, record):
        if self.use_color and record.levelno in self.FORMATS:
            return logging.Formatter(
                ''.join([self.opener, self.FORMATS.get(record.levelno), "%(message)s", Colors.reset, self.CLOSER])
            ).format(record)
        else:
            return logging.Formatter(''.join([self.opener, "%(message)s", self.CLOSER])).format(record)


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


def _stdout_is_journal() -> bool:
    """True only when stdout really is systemd's journal. JOURNAL_STREAM is inherited by child processes (a desktop
    session launched by systemd passes it to every terminal), so it's compared with stdout's device and inode, as
    systemd's documentation recommends."""
    stream = os.environ.get('JOURNAL_STREAM', '')
    try:
        device, inode = (int(part) for part in stream.split(':'))
        stat = os.fstat(sys.stdout.fileno())
    except (ValueError, OSError):
        return False
    return (stat.st_dev, stat.st_ino) == (device, inode)


def _get_console_handler() -> logging.StreamHandler:
    """
    Internal function for generating a streamhandler.

    Returns
    -------
    StreamHandler
    """
    console_handler = logging.StreamHandler(sys.stdout)
    # Under systemd the journal stamps every line itself, and doesn't render color codes
    under_journal = _stdout_is_journal()
    console_handler.setFormatter(StreamFormatter(use_color=not under_journal, timestamp=not under_journal))
    if under_journal:
        # Debug detail still goes to data/app.log; the journal gets the readable summary
        console_handler.setLevel(logging.INFO)
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
