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


def digest_deploy(token: str) -> dict:
    """Netlify's file-digest deploy: the list of every file's SHA-1 goes up, and only the files Netlify doesn't have
    yet are uploaded (Oct 7: the zip deploy sent the whole site every hour; with story pages kept for good, it would
    have grown past 100 MB a run). Raises on any failure."""
    import time
    from urllib.parse import quote
    headers = {'Authorization': f'Bearer {token}'}
    files = digests()
    response = rq.post(f'{NETLIFY_API}/sites/{NETLIFY_SITE}/deploys', json={'files': files, 'async': True},
                       headers=headers, timeout=120)
    response.raise_for_status()
    deploy = response.json()
    deadline = time.time() + 300
    while deploy.get('state') not in ('prepared', 'uploading', 'uploaded', 'ready') and time.time() < deadline:
        if deploy.get('state') == 'error':
            raise RuntimeError(f"netlify deploy failed: {deploy.get('error_message')}")
        time.sleep(2)
        deploy = rq.get(f"{NETLIFY_API}/deploys/{deploy['id']}", headers=headers, timeout=60).json()
    required = set(deploy.get('required') or [])
    by_sha = {}
    for path, sha in files.items():
        by_sha.setdefault(sha, path)  # one copy of each content is enough
    sent = 0
    for sha in required:
        path = by_sha[sha]
        with open(os.path.join(Config.build, path.lstrip('/')), 'rb') as f:
            body = f.read()
        r = rq.put(f"{NETLIFY_API}/deploys/{deploy['id']}/files/{quote(path.lstrip('/'))}", data=body, timeout=120,
                   headers={**headers, 'Content-Type': 'application/octet-stream'})
        r.raise_for_status()
        sent += len(body)
    while deploy.get('state') != 'ready' and time.time() < deadline:
        if deploy.get('state') == 'error':
            raise RuntimeError(f"netlify deploy failed: {deploy.get('error_message')}")
        time.sleep(2)
        deploy = rq.get(f"{NETLIFY_API}/deploys/{deploy['id']}", headers=headers, timeout=60).json()
    if deploy.get('state') != 'ready':
        raise RuntimeError(f"netlify deploy not ready after 5 minutes ({deploy.get('state')})")
    logger.info("Deployed %s: %d files, %d new or changed (%.1f MB sent): %s", deploy.get('id'), len(files),
                len(required), sent / 1e6, deploy.get('ssl_url') or deploy.get('url'))
    return deploy


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
