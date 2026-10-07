import os

from hypothesis import given, strategies, settings
from jinja2 import Template

from app.site.common import TemplateHandler, PathHandler
from app.utils.config import Config


def test_template_instantiation():
    test = TemplateHandler('test.html')
    assert isinstance(test, TemplateHandler)
    assert test.template_name == 'test.html'
    assert test.template is not None
    assert isinstance(test.template, Template)


@settings(deadline=None)
@given(strategies.text())
def test_template_render(s):
    test = TemplateHandler('test.html')
    assert test.render({'test': s}) == s


@settings(deadline=None)
@given(strategies.text())
def test_template_write(s):
    test = TemplateHandler('test.html')
    test.write({'test': s})

    # Read back exactly what was written: text mode would turn '\r\n' into '\n'
    with open(test.path, encoding='utf-8', newline='') as f_in:
        assert f_in.read() == s


def test_pathhandler():
    ph = PathHandler('test.png')
    assert isinstance(ph, PathHandler)
    assert ph.path == 'test.png'
    assert ph.build == os.path.join(Config.build, 'test.png')

