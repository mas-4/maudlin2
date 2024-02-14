import os
import string

import yaml

from app import j2env
from app.config import Config
from app.constants import Constants
from app.logger import get_logger

logger = get_logger(__name__)


class Blog:
    page = j2env.get_template('blog.html')
    index = j2env.get_template('blog.index.html')

    def __init__(self):
        self.posts = []

    def generate(self):
        logger.info("Generating blog...")
        self.load_posts()
        self.render_blog_index()
        self.render_blog()
        logger.info("...done")

    def load_posts(self):
        path = os.path.join(Constants.Paths.ROOT, 'app', 'posts')
        for file in os.listdir(path):
            with open(os.path.join(path, file), 'rt') as f:
                frontmatter, post = self.read_frontmatter(f.read())
            url = frontmatter['title'].lower()
            for item in string.punctuation + ' ':
                url = url.replace(item, '-')
            url = url.strip('-') + '.html'

            self.posts.append({
                'title': frontmatter['title'],
                'date': frontmatter['date'],
                'body': post,
                'url': url
            })

    @staticmethod
    def read_frontmatter(post):
        frontmatter = post.split('---')[1]
        post = post.split('---')[2]
        frontmatter: dict = yaml.safe_load(frontmatter)
        return frontmatter, post

    def render_blog_index(self):
        with open(os.path.join(Config.build, 'blog.html'), 'wt') as f:
            f.write(self.index.render(posts=self.posts))

    def render_blog(self):
        for post in self.posts:
            with open(os.path.join(Config.build, post['url']), 'wt') as f:
                f.write(self.page.render(post=post))
