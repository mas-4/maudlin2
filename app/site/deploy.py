import io
import os
import shutil
import zipfile

import requests as rq

from app.utils.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

NETLIFY_API = 'https://api.netlify.com/api/v1'
# Netlify accepts the site's id or its netlify.app domain here
NETLIFY_SITE = os.environ.get('NETLIFY_SITE', 'maudlin.netlify.app')
# Cloudflare sits in front of Netlify and keeps each page for an hour (Oct 30, the person: "we update once an hour why
# don't we cache for at least 45 minutes"); after each deploy its copies are cleared so the new build shows at once
CLOUDFLARE_API = 'https://api.cloudflare.com/client/v4'
CLOUDFLARE_ZONE = os.environ.get('CLOUDFLARE_ZONE', 'b17054eff5fdc840a8d9c72d29b25f01')  # bignews.day's zone (not a secret)


def move_to_public():
    server_location = os.environ.get('SERVER_LOCATION', None)
    if server_location is None:
        logger.warning("No server location specified, not moving files")
        return

    for file in os.listdir(Config.build):
        logger.debug("Moving %s", file)
        shutil.move(os.path.join(Config.build, file), os.path.join(server_location, file))


def zip_build() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(Config.build):
            for name in files:
                path = os.path.join(root, name)
                archive.write(path, os.path.relpath(path, Config.build))
    return buffer.getvalue()


def digests() -> dict[str, str]:
    """Every built file's path on the site ('/story-12.html') and the SHA-1 of its contents"""
    import hashlib
    out = {}
    for root, _, files in os.walk(Config.build):
        for name in files:
            path = os.path.join(root, name)
            with open(path, 'rb') as f:
                out['/' + os.path.relpath(path, Config.build).replace(os.sep, '/')] = hashlib.sha1(f.read()).hexdigest()
    return out


def wait_for(deploy: dict, states: tuple, headers: dict, minutes: float, what: str) -> dict:
    """Poll a Netlify deploy until it reaches one of `states`, for at most `minutes`"""
    import time
    deadline = time.time() + minutes * 60
    while deploy.get('state') not in states:
        if deploy.get('state') == 'error':
            raise RuntimeError(f"netlify deploy failed: {deploy.get('error_message')}")
        if time.time() >= deadline:
            raise RuntimeError(f"netlify deploy not {what} after {minutes:g} minutes ({deploy.get('state')})")
        time.sleep(2)
        deploy = rq.get(f"{NETLIFY_API}/deploys/{deploy['id']}", headers=headers, timeout=60).json()
    return deploy


# Uploads at once: Netlify's own cli sends 5 (Oct 30: one at a time, ~400 files took 150-200 s an hour)
UPLOADERS = 5
UPLOAD_TRIES = 4


def upload(deploy_id: str, path: str, headers: dict) -> int:
    """PUT one file into a deploy and return its size. A 429 waits out Netlify's rate limit; a 5xx or dropped
    connection is tried again (Oct 28 02:16: one 500 on one file sent the whole site up as a zip)"""
    import time
    from urllib.parse import quote
    with open(os.path.join(Config.build, path.lstrip('/')), 'rb') as f:
        body = f.read()
    url = f"{NETLIFY_API}/deploys/{deploy_id}/files/{quote(path.lstrip('/'))}"
    for attempt in range(1, UPLOAD_TRIES + 1):
        try:
            r = rq.put(url, data=body, timeout=120, headers={**headers, 'Content-Type': 'application/octet-stream'})
        except (rq.ConnectionError, rq.Timeout):
            if attempt == UPLOAD_TRIES:
                raise
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429 and attempt < UPLOAD_TRIES:
            time.sleep(rate_limit_wait(r))
            continue
        if r.status_code >= 500 and attempt < UPLOAD_TRIES:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return len(body)
    raise AssertionError('unreachable')


def rate_limit_wait(r) -> float:
    """Seconds until Netlify lifts a rate limit: its X-RateLimit-Reset (a unix time) or Retry-After, else 10 s,
    and never more than a minute"""
    import time
    headers = getattr(r, 'headers', None) or {}
    try:
        if headers.get('X-RateLimit-Reset'):
            return min(60.0, max(1.0, float(headers['X-RateLimit-Reset']) - time.time()))
        if headers.get('Retry-After'):
            return min(60.0, max(1.0, float(headers['Retry-After'])))
    except ValueError:
        pass
    return 10.0


def digest_deploy(token: str) -> dict:
    """Netlify's file-digest deploy: the list of every file's SHA-1 goes up, and only the files Netlify doesn't have
    yet are uploaded (Oct 7: the zip deploy sent the whole site every hour; with story pages kept for good, it would
    have grown past 100 MB a run). Preparing and finishing each get their own 5 minutes, so slow uploads don't eat
    the wait after them (Oct 8 00:11: ~24 MB of uploads used up one shared 5 minutes). Raises on any failure."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    headers = {'Authorization': f'Bearer {token}'}
    files = digests()
    response = rq.post(f'{NETLIFY_API}/sites/{NETLIFY_SITE}/deploys', json={'files': files, 'async': True},
                       headers=headers, timeout=120)
    response.raise_for_status()
    deploy = wait_for(response.json(), ('prepared', 'uploading', 'uploaded', 'ready'), headers, 5, 'prepared')
    required = set(deploy.get('required') or [])
    by_sha = {}
    for path, sha in files.items():
        by_sha.setdefault(sha, path)  # one copy of each content is enough
    started = time.time()
    sent = 0
    with ThreadPoolExecutor(UPLOADERS) as pool:
        uploads = [pool.submit(upload, deploy['id'], by_sha[sha], headers) for sha in required]
        try:
            for done in as_completed(uploads):
                sent += done.result()
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)  # a file that won't go up fails the deploy; don't send the rest
            raise
    uploading = time.time() - started
    deploy = wait_for(deploy, ('ready',), headers, 5, 'ready')
    logger.info("Deployed %s: %d files, %d new or changed (%.1f MB sent in %.0f s): %s", deploy.get('id'), len(files),
                len(required), sent / 1e6, uploading, deploy.get('ssl_url') or deploy.get('url'))
    return deploy


def purge_cloudflare():
    """Clear Cloudflare's cached copies of the whole site once a deploy is live. Never raises: if it fails, the cache
    rule's one-hour limit still brings the new build within the hour."""
    if not (Config.cloudflare and CLOUDFLARE_ZONE):
        return
    try:
        r = rq.post(f'{CLOUDFLARE_API}/zones/{CLOUDFLARE_ZONE}/purge_cache', json={'purge_everything': True},
                    headers={'Authorization': f'Bearer {Config.cloudflare}'}, timeout=60)
        if r.status_code >= 400 or not r.json().get('success'):
            logger.warning("Cloudflare purge failed (%s): %s", r.status_code, r.text[:300])
            return
        logger.info("Cleared Cloudflare's cache")
    except Exception as e:  # noqa: BLE001 - the deploy itself went fine
        logger.warning("Cloudflare purge failed: %s", e)


def publish_to_netlify():
    """Deploy the built site straight to production through Netlify's api (no cli needed): only the files that
    changed (digest_deploy), or if that fails the whole site as a zip. A failed deploy raises, so the run exits
    non-zero and the health check reports it."""
    if not Config.netlify:
        logger.warning("No netlify credentials found, not publishing to netlify")
        move_to_public()
        return
    try:
        digest_deploy(Config.netlify)
        purge_cloudflare()
        return
    except Exception as e:  # noqa: BLE001 - the zip deploy still works
        logger.warning("Digest deploy failed (%s); sending the whole site as a zip", e)
    body = zip_build()
    logger.info("Publishing %.1f MB to netlify site %s", len(body) / 1e6, NETLIFY_SITE)
    response = rq.post(f'{NETLIFY_API}/sites/{NETLIFY_SITE}/deploys', data=body, timeout=300, headers={
        'Authorization': f'Bearer {Config.netlify}',
        'Content-Type': 'application/zip',
    })
    response.raise_for_status()
    deploy = response.json()
    logger.info("Deployed %s (%s): %s", deploy.get('id'), deploy.get('state'), deploy.get('ssl_url') or deploy.get('url'))
    purge_cloudflare()
