"""app/analysis/motif_actions.py: the table of actions the checker and the MCP server send."""
import ast
import os
import re

import pytest

from app.analysis import motif_actions as ma
from app.analysis import motif_index as mi


def mcp_doc() -> str:
    path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'maudlin_mcp.py')
    tree = ast.parse(open(path).read())
    return next(ast.get_docstring(n) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'checker_action')


def test_the_mcp_tool_names_every_action_and_no_other():
    """The MCP tool's docstring was the only list of the actions until Oct 21; now it must match the table"""
    named = set(re.findall(r'(?<![\w"$])([a-z_]+)(?= \{| / [a-z_]+ \{)', mcp_doc()))
    assert named == set(ma.names())


def test_every_verb_in_the_table_exists():
    for name, (fields, run) in ma.ACTIONS.items():
        assert callable(run), name
        assert set(fields.values()) <= {'motif', 'group', 'text', 'str', 'words', 'facet'}, name


def test_an_action_checks_its_fields_before_anything_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 2, 'claims': {mi.key('a'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'one', 'claims': [{'claim': 'a', 'source': 's'}]}}})
    with pytest.raises(ValueError, match='unknown action'):
        ma.apply({'action': 'nope'})
    with pytest.raises(ValueError, match=r'move: missing or wrong target \(motif\)'):
        ma.apply({'action': 'move', 'claim': 'a', 'source': 'M001', 'target': 'M999'})
    with pytest.raises(ValueError, match=r'rename: missing or wrong name \(text\)'):
        ma.apply({'action': 'rename', 'id': 'M001', 'name': '   '})
    assert mi.load()['entries']['M001']['name'] == 'one'
    ma.apply({'action': 'rename', 'id': 'M001', 'name': 'One'})
    assert mi.load()['entries']['M001']['name'] == 'One'
    seen = []
    ma.apply({'action': 'check', 'claim': 'a', 'id': 'M001', 'answer': 'yes'}, on_check=seen.append)
    assert [s['answer'] for s in seen] == ['yes']
