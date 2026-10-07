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


def publish_to_netlify():
    """Deploy the built site straight to production through Netlify's zip deploy api (no cli needed). A failed
    deploy raises, so the run exits non-zero and the health check reports it."""
    if not Config.netlify:
        logger.warning("No netlify credentials found, not publishing to netlify")
        move_to_public()
        return
    body = zip_build()
    logger.info("Publishing %.1f MB to netlify site %s", len(body) / 1e6, NETLIFY_SITE)
    response = rq.post(f'{NETLIFY_API}/sites/{NETLIFY_SITE}/deploys', data=body, timeout=300, headers={
        'Authorization': f'Bearer {Config.netlify}',
        'Content-Type': 'application/zip',
    })
    response.raise_for_status()
    deploy = response.json()
    logger.info("Deployed %s (%s): %s", deploy.get('id'), deploy.get('state'), deploy.get('ssl_url') or deploy.get('url'))
