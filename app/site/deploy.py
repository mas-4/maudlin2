import os
import shutil

from app.utils import get_logger, Config, Constants

logger = get_logger(__name__)


def move_to_public():
    server_location = os.environ.get('SERVER_LOCATION', None)
    if server_location is None:
        logger.warning("No server location specified, not moving files")
        return

    for file in os.listdir(Config.build):
        logger.debug(f"Moving %s", file)
        shutil.move(os.path.join(Config.build, file), os.path.join(server_location, file))


def publish_to_netlify():
    if Config.netlify:
        logger.info("Publishing to netlify")
        os.environ['NETLIFY_AUTH_TOKEN'] = Config.netlify
        os.system(f'cd {Constants.Paths.ROOT} && netlify deploy --dir={Config.build} --prod')
        return
    logger.warning("No netlify credentials found, not publishing to netlify")
    move_to_public()