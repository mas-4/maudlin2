import os
import pathlib
import re
from enum import Enum, auto


class Bias(Enum):
    extreme_left = auto()
    left = auto()
    left_center = auto()
    center = auto()
    right_center = auto()
    right = auto()
    extreme_right = auto()

    def __str__(self):
        return self.name.replace('_', ' ').title()

class Credibility(Enum):
    very_low = auto()
    low = auto()
    mixed = auto()
    mostly_factual = auto()
    high = auto()
    very_high = auto()

    def __str__(self):
        return self.name.replace('_', ' ').title()

class Constants:
    class Paths:
        ROOT = str(pathlib.Path(__file__).parent.parent)
        EMAIL_CREDS = os.path.join(ROOT, '.creds')
        DAY_REPORT = os.path.join(ROOT, 'data', 'day-report.txt')

    class Patterns:
        DATE_URL = re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')