"""app/site/deploy.py: the digest deploy sends every file's SHA-1 and uploads only what Netlify asks for; if it fails,
the whole site goes up as a zip, as before."""
import hashlib

from app.site import deploy
from app.utils.config import Config


class Resp:
    def __init__(self, data=None, status=200):
        self.data, self.status_code = data or {}, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def site(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    (tmp_path / 'index.html').write_text('front')
    (tmp_path / 'story-1.html').write_text('old story')
    (tmp_path / '2026' / '10' / '04').mkdir(parents=True)
    (tmp_path / '2026' / '10' / '04' / 'index.html').write_text('edition')
    monkeypatch.setattr('time.sleep', lambda s: None)


def test_only_what_netlify_lacks_is_uploaded(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch)
    sent, puts = {}, []

    def post(url, json=None, headers=None, timeout=None, data=None):
        sent.update(json['files'])
        return Resp({'id': 'd1', 'state': 'prepared', 'required': [hashlib.sha1(b'front').hexdigest()]})
    monkeypatch.setattr(deploy.rq, 'post', post)
    monkeypatch.setattr(deploy.rq, 'put', lambda url, data=None, timeout=None, headers=None: puts.append((url, data)) or Resp())
    monkeypatch.setattr(deploy.rq, 'get', lambda url, headers=None, timeout=None: Resp({'id': 'd1', 'state': 'ready'}))
    deploy.digest_deploy('token')
    assert set(sent) == {'/index.html', '/story-1.html', '/2026/10/04/index.html'}
    assert puts == [('https://api.netlify.com/api/v1/deploys/d1/files/index.html', b'front')]  # the rest it already has


def test_a_failed_digest_deploy_falls_back_to_the_zip(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch)
    monkeypatch.setattr(Config, 'netlify', 'token')
    zipped = []
    monkeypatch.setattr(deploy, 'digest_deploy', lambda token: (_ for _ in ()).throw(RuntimeError('api down')))
    monkeypatch.setattr(deploy.rq, 'post', lambda url, data=None, timeout=None, headers=None: zipped.append(headers['Content-Type']) or Resp({'id': 'z'}))
    deploy.publish_to_netlify()
    assert zipped == ['application/zip']
