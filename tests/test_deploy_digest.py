"""app/site/deploy.py: the digest deploy sends every file's SHA-1 and uploads only what Netlify asks for; if it fails,
the whole site goes up as a zip, as before."""
import hashlib

from app.site import deploy
from app.utils.config import Config


class Resp:
    def __init__(self, data=None, status=200):
        self.data, self.status_code, self.text = data or {}, status, str(data)

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


def test_slow_uploads_dont_use_up_the_wait_after_them(tmp_path, monkeypatch):
    """Oct 8 00:11: uploads took most of one shared 5 minutes, so the deploy was given up while Netlify finished"""
    site(tmp_path, monkeypatch)
    clock = [0.0]
    monkeypatch.setattr('time.time', lambda: clock[0])
    states = iter(['processing', 'processing', 'ready'])

    def put(url, data=None, timeout=None, headers=None):
        clock[0] += 240  # each upload takes 4 minutes
        return Resp()
    monkeypatch.setattr(deploy.rq, 'post', lambda url, json=None, headers=None, timeout=None: Resp(
        {'id': 'd1', 'state': 'prepared', 'required': [hashlib.sha1(b'front').hexdigest(),
                                                       hashlib.sha1(b'old story').hexdigest()]}))
    monkeypatch.setattr(deploy.rq, 'put', put)
    monkeypatch.setattr(deploy.rq, 'get', lambda url, headers=None, timeout=None: Resp({'id': 'd1', 'state': next(states)}))
    assert deploy.digest_deploy('token')['state'] == 'ready'


def test_a_deploy_that_never_finishes_gives_up(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch)
    clock = [0.0]
    monkeypatch.setattr('time.time', lambda: clock[0])
    monkeypatch.setattr('time.sleep', lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(deploy.rq, 'post', lambda url, json=None, headers=None, timeout=None: Resp({'id': 'd1', 'state': 'prepared', 'required': []}))
    monkeypatch.setattr(deploy.rq, 'get', lambda url, headers=None, timeout=None: Resp({'id': 'd1', 'state': 'processing'}))
    try:
        deploy.digest_deploy('token')
    except RuntimeError as e:
        assert 'not ready after 5 minutes' in str(e)
    else:
        raise AssertionError('should have given up')


def test_cloudflare_is_cleared_after_a_deploy(tmp_path, monkeypatch):
    """Oct 30: Cloudflare keeps pages an hour; a finished deploy clears its copies so the new build shows at once"""
    site(tmp_path, monkeypatch)
    monkeypatch.setattr(Config, 'netlify', 'token')
    monkeypatch.setattr(Config, 'cloudflare', 'cf-token')
    monkeypatch.setattr(deploy, 'CLOUDFLARE_ZONE', 'zone1')
    monkeypatch.setattr(deploy, 'digest_deploy', lambda token: {'state': 'ready'})
    purged = []
    monkeypatch.setattr(deploy.rq, 'post', lambda url, json=None, headers=None, timeout=None: purged.append((url, json)) or Resp({'success': True}))
    deploy.publish_to_netlify()
    assert purged == [('https://api.cloudflare.com/client/v4/zones/zone1/purge_cache', {'purge_everything': True})]


def test_a_failed_purge_never_fails_the_run(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch)
    monkeypatch.setattr(Config, 'cloudflare', 'cf-token')
    monkeypatch.setattr(deploy, 'CLOUDFLARE_ZONE', 'zone1')
    monkeypatch.setattr(deploy.rq, 'post', lambda *a, **k: (_ for _ in ()).throw(ConnectionError('down')))
    deploy.purge_cloudflare()
    monkeypatch.setattr(deploy.rq, 'post', lambda *a, **k: Resp({'success': False}, 403))
    deploy.purge_cloudflare()


def test_no_purge_without_a_token_or_zone(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'cloudflare', '')
    monkeypatch.setattr(deploy, 'CLOUDFLARE_ZONE', 'zone1')
    monkeypatch.setattr(deploy.rq, 'post', lambda *a, **k: (_ for _ in ()).throw(AssertionError('called')))
    deploy.purge_cloudflare()


def stub_deploy(monkeypatch, required):
    monkeypatch.setattr(deploy.rq, 'post', lambda url, json=None, headers=None, timeout=None: Resp(
        {'id': 'd1', 'state': 'prepared', 'required': [hashlib.sha1(c).hexdigest() for c in required]}))
    monkeypatch.setattr(deploy.rq, 'get', lambda url, headers=None, timeout=None: Resp({'id': 'd1', 'state': 'ready'}))


def test_uploads_go_several_at_a_time(tmp_path, monkeypatch):
    """Oct 30: one PUT at a time, ~400 changed files took 150-200 s of every hour"""
    import threading
    site(tmp_path, monkeypatch)
    for i in range(12):
        (tmp_path / f'story-{i + 2}.html').write_text(f'story {i}')
    stub_deploy(monkeypatch, [f'story {i}'.encode() for i in range(12)])
    lock, now, most, puts = threading.Lock(), [0], [0], []

    def put(url, data=None, timeout=None, headers=None):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        threading.Event().wait(0.05)  # time.sleep is stubbed out
        with lock:
            now[0] -= 1
            puts.append(url)
        return Resp()
    monkeypatch.setattr(deploy.rq, 'put', put)
    deploy.digest_deploy('token')
    assert len(puts) == 12
    assert 1 < most[0] <= deploy.UPLOADERS


def test_a_failed_upload_is_tried_again(tmp_path, monkeypatch):
    """Oct 28 02:16: one 500 on one file sent the whole site up as a zip"""
    site(tmp_path, monkeypatch)
    stub_deploy(monkeypatch, [b'front'])
    answers = iter([Resp(status=500), Resp(status=429), ConnectionError, Resp()])

    def put(url, data=None, timeout=None, headers=None):
        a = next(answers)
        if a is ConnectionError:
            raise deploy.rq.ConnectionError('reset')
        return a
    monkeypatch.setattr(deploy.rq, 'put', put)
    assert deploy.digest_deploy('token')['state'] == 'ready'


def test_an_upload_that_keeps_failing_fails_the_deploy(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch)
    stub_deploy(monkeypatch, [b'front', b'old story', b'edition'])
    puts = []
    monkeypatch.setattr(deploy.rq, 'put', lambda url, data=None, timeout=None, headers=None: puts.append(url) or Resp(status=503))
    try:
        deploy.digest_deploy('token')
    except RuntimeError as e:
        assert '503' in str(e)
    else:
        raise AssertionError('should have failed')
    assert len(puts) <= 3 * deploy.UPLOAD_TRIES


def test_rate_limit_wait_reads_netlifys_headers(monkeypatch):
    monkeypatch.setattr('time.time', lambda: 1000.0)

    class R:
        def __init__(self, headers):
            self.headers = headers
    assert deploy.rate_limit_wait(R({'X-RateLimit-Reset': '1012'})) == 12
    assert deploy.rate_limit_wait(R({'Retry-After': '3'})) == 3
    assert deploy.rate_limit_wait(R({'X-RateLimit-Reset': '99999'})) == 60
    assert deploy.rate_limit_wait(R({})) == 10
