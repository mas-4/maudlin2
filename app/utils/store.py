"""The JSON files the app keeps in its data folder: read with a fallback, written all at once, and a lock for files
that more than one process changes. Paths are taken at call time, so tests can point a module's path elsewhere."""
import contextlib
import copy
import fcntl
import json
import os
import secrets


def read_json(path: str, default=None):
    """The file's contents, or a fresh copy of default (called, if it's a function) when the file is missing or isn't
    valid JSON."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default() if callable(default) else copy.deepcopy(default)


def write_json(path: str, data, indent=None, **kwargs):
    """Write data as JSON so that a reader sees the old file or the new one, never half of one: into a temporary file
    beside it, then renamed over it. Makes the folder if it's missing. Other arguments go to json.dump."""
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.{secrets.token_hex(4)}.tmp'
    # Opened like open() would (the umask decides the mode), so the new file has the permissions the old one had
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=indent, **kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def locked(path: str):
    """One writer at a time for a file several processes read, change and save: an exclusive lock on path + '.lock',
    held until the block ends. Not reentrant: don't take it again inside the block."""
    with open(path + '.lock', 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
