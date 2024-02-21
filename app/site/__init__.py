import os
from app.utils import Constants

from jinja2 import Environment, FileSystemLoader

j2env = Environment(loader=FileSystemLoader(os.path.join(Constants.Paths.ROOT, 'app', 'site', 'templates')),
                    trim_blocks=True)

__all__ = ['j2env']
