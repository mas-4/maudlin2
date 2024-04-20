import os

from hypothesis import given, strategies
from jinja2 import Template

from app.site.common import TemplateHandler, PathHandler
from app.utils.config import Config


def test_template_instantiation():
    test = TemplateHandler('test.html')
    assert isinstance(test, TemplateHandler)
    assert test.template_name == 'test.html'
    assert test.template is not None
    assert isinstance(test.template, Template)


@given(strategies.text())
def test_template_render(s):
    test = TemplateHandler('test.html')
    assert test.render({'test': s}) == s


@given(strategies.text())
def test_template_write(s):
    test = TemplateHandler('test.html')
    test.write({'test': s})

    def replace(x): return x.replace('\r', '\n')

    with open(test.path, 'rt', encoding='utf-8') as f_in:
        # Mac changes \r to \n in text files. Very weird. Not much on Google about it.
        assert replace(f_in.read()) == replace(s)


def test_pathhandler():
    ph = PathHandler('test.png')
    assert isinstance(ph, PathHandler)
    assert ph.path == 'test.png'
    assert ph.build == os.path.join(Config.build, 'test.png')