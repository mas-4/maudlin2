from app.site.common import TemplateHandler
from jinja2 import Template
from hypothesis import given, strategies
import tempfile


def test_instantiation():
    test = TemplateHandler('test.html')
    assert isinstance(test, TemplateHandler)
    assert test.template_name == 'test.html'
    assert test.template is not None
    assert isinstance(test.template, Template)


@given(strategies.text())
def test_render(s):
    test = TemplateHandler('test.html')
    assert test.render({'test': s}) == s


@given(strategies.text())
def test_write(s):
    test = TemplateHandler('test.html')
    with tempfile.TemporaryDirectory() as tmpdir:
        test.write({'test': s}, f'{tmpdir}/test.html')
        with open(f'{tmpdir}/test.html', 'rt') as f_in:
            # Mac changes \r to \n in text files. Very weird. Not much on Google about it.
            assert f_in.read().replace('\n', '\r') == s
