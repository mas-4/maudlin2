"""app/utils/store: JSON files read with a fallback and written atomically."""
import json
import os

import pytest

from app.utils import store


def test_write_then_read(tmp_path):
    path = str(tmp_path / 'a.json')
    store.write_json(path, {'x': [1, 2]})
    assert store.read_json(path, {}) == {'x': [1, 2]}
    assert open(path).read() == '{"x": [1, 2]}'


def test_indent_and_json_arguments_kept(tmp_path):
    path = str(tmp_path / 'a.json')
    store.write_json(path, {'b': 1, 'a': 'é'}, indent=1, sort_keys=True, ensure_ascii=False)
    assert open(path, encoding='utf-8').read() == '{\n "a": "é",\n "b": 1\n}'


def test_write_leaves_no_temporary_file(tmp_path):
    path = str(tmp_path / 'a.json')
    store.write_json(path, [1])
    store.write_json(path, [2])
    assert os.listdir(tmp_path) == ['a.json']
    assert store.read_json(path) == [2]


def test_failed_write_keeps_the_old_file(tmp_path):
    path = str(tmp_path / 'a.json')
    store.write_json(path, {'ok': True})
    with pytest.raises(TypeError):
        store.write_json(path, {'bad': object()})
    assert os.listdir(tmp_path) == ['a.json']
    assert store.read_json(path) == {'ok': True}


def test_write_makes_the_folder(tmp_path):
    path = str(tmp_path / 'new' / 'deeper' / 'a.json')
    store.write_json(path, {})
    assert json.load(open(path)) == {}


def test_written_file_has_the_usual_permissions(tmp_path):
    path = str(tmp_path / 'a.json')
    store.write_json(path, {})
    plain = str(tmp_path / 'plain')
    open(plain, 'w').close()
    assert os.stat(path).st_mode == os.stat(plain).st_mode


def test_default_on_missing_or_corrupt(tmp_path):
    missing = str(tmp_path / 'missing.json')
    assert store.read_json(missing, {'n': 1}) == {'n': 1}
    assert store.read_json(missing) is None
    corrupt = tmp_path / 'corrupt.json'
    corrupt.write_text('{"half": ')
    assert store.read_json(str(corrupt), []) == []
    assert store.read_json(str(tmp_path), 'folder') == 'folder'  # unreadable: a folder, not a file


def test_default_is_a_fresh_copy(tmp_path):
    missing = str(tmp_path / 'missing.json')
    default = {'threads': {}}
    first = store.read_json(missing, default)
    first['threads']['t1'] = 1
    assert default == {'threads': {}}
    assert store.read_json(missing, default) == {'threads': {}}


def test_callable_default_is_called(tmp_path):
    missing = str(tmp_path / 'missing.json')
    assert store.read_json(missing, dict) == {}
    assert store.read_json(missing, lambda: {'next': 1}) == {'next': 1}


def test_locked_takes_a_lock_file_beside_the_file(tmp_path):
    path = str(tmp_path / 'a.json')
    with store.locked(path):
        store.write_json(path, 1)
    assert sorted(os.listdir(tmp_path)) == ['a.json', 'a.json.lock']
