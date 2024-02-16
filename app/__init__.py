import os
import pathlib

import nltk
from jinja2 import Environment, FileSystemLoader

nltk.download('vader_lexicon')
nltk.download('averaged_perceptron_tagger')

here = pathlib.Path(__file__).parent.resolve()
j2env = Environment(loader=FileSystemLoader(os.path.join(here, 'templates')), trim_blocks=True)