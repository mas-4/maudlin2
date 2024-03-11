import gzip
import shutil
import dropbox
from app.utils.config import Config

def gzip_file(source, destination):
    with open(source, 'rb') as f_in, gzip.open(destination, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)  # noqa stfu pylint


def push_to_dropbox(file, destination, token):
    dbx = dropbox.Dropbox(token)
    with open(file, 'rb') as f:
        dbx.files_upload(f.read(), destination, mode=dropbox.files.WriteMode.overwrite)


def backup():
    backup_name = Config.db_file_name + '.gz'
    backup_path = f'{Config.output_dir}/{backup_name}'
    gzip_file(Config.db_file_path, backup_path)
    push_to_dropbox(backup_path, f'/Apps/maudlin/{backup_name}', Config.dropbox)
    print('Backup complete')

if __name__ == '__main__':
    backup()