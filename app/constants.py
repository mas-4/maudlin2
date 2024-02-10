import os
import pathlib
import re
from enum import Enum, auto


class Bias(Enum):
    extreme_left = -3
    left = -2
    left_center = -1
    unbiased = 0
    right_center = 1
    right = 2
    extreme_right = 3

    def __str__(self):
        return self.name.replace('_', ' ').title()

    @classmethod
    def to_dict(cls):
        return {str(e.value): str(e) for e in cls}

class Credibility(Enum):
    very_low = 0
    low = 1
    mixed = 2
    mostly_factual = 3
    high = 4
    very_high = 5

    def __str__(self):
        return self.name.replace('_', ' ').title()

    @classmethod
    def to_dict(cls):
        return {str(e.value): str(e) for e in cls}


class Constants:
    class Paths:
        ROOT = str(pathlib.Path(__file__).parent.parent)
        EMAIL_CREDS = os.path.join(ROOT, '.creds')

    class Patterns:
        DATE_URL = re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')