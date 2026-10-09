import pytest

from app import builder


def test_the_upload_aside_raises_its_failure_on_join(monkeypatch):
    def fail():
        raise RuntimeError('deploy failed')
    monkeypatch.setattr(builder, 'publish_to_netlify', fail)
    with pytest.raises(RuntimeError, match='deploy failed'):
        builder.Upload().join()


def test_the_upload_aside_runs(monkeypatch):
    ran = []
    monkeypatch.setattr(builder, 'publish_to_netlify', lambda: ran.append(1))
    builder.Upload().join()
    assert ran == [1]
