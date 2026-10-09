"""The GPU lease (Oct 9, the person: "an experiment mode flag that reduces the work time of the worker service, like
a semaphore"). An experiment takes the lease for a while; the worker (app/worker.py) finishes the step it's on and
starts no other until it's given back, as it waits for the hourly run. A lease always runs out (MAX_MINUTES at most,
renewed while its holder lives), so an experiment that crashes can't keep production work waiting.

    python -m app.gpu_lease run --minutes 45 -- .venv/bin/python -u scripts/experiments/x.py
    python -m app.gpu_lease status

`run` waits for the hourly run to be over first, takes the lease, waits for the worker to finish the step it's on (its
models may still fill the card), holds the lease while the command runs, renews it every minute up to
its minutes, and gives it back when the command ends (or the minutes are up: then the command is stopped)."""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime as dt

from app.utils import Config

LEASE = os.path.join(Config.data, 'gpu_lease.json')  # {'holder', 'pid', 'until', 'since'}
MAX_MINUTES = 120
RENEW = 60  # seconds between renewals while the holder lives
STALE = 3 * RENEW  # a lease not renewed this long is dropped (its holder died)


def held() -> dict | None:
    """The lease if someone holds it now: not past its time, renewed lately, its process alive"""
    try:
        with open(LEASE) as f:
            lease = json.load(f)
    except (OSError, ValueError):
        return None
    now = time.time()
    if lease.get('until', 0) < now or now - lease.get('renewed', 0) > STALE:
        return None
    try:
        os.kill(lease['pid'], 0)
    except (OSError, KeyError, TypeError):
        return None
    return lease


def _write(lease: dict):
    tmp = LEASE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(lease, f)
    os.replace(tmp, LEASE)


def release(pid: int | None = None):
    """Give the lease back (only its holder's, when `pid` is given)"""
    lease = held()
    if lease is None or pid is None or lease.get('pid') == pid:
        try:
            os.remove(LEASE)
        except OSError:
            pass


class Hold:
    """Hold the lease inside, renewed every RENEW seconds, for at most `minutes`"""

    def __init__(self, holder: str, minutes: float):
        self.holder, self.minutes = holder, min(float(minutes), MAX_MINUTES)

    def __enter__(self):
        other = held()
        if other is not None and other.get('pid') != os.getpid():
            raise RuntimeError(f"the GPU lease is held by {other.get('holder')} until "
                               f"{dt.fromtimestamp(other['until']).strftime('%H:%M')}")
        self.until = time.time() + self.minutes * 60
        self.lease = {'holder': self.holder, 'pid': os.getpid(), 'until': self.until,
                      'since': dt.now().isoformat(timespec='seconds'), 'renewed': time.time()}
        _write(self.lease)
        self.done = threading.Event()
        self.renewer = threading.Thread(target=self._renew, daemon=True)
        self.renewer.start()
        return self

    def _renew(self):
        while not self.done.wait(RENEW):
            if time.time() >= self.until:
                return
            _write({**self.lease, 'renewed': time.time()})

    def __exit__(self, *exc):
        self.done.set()
        release(os.getpid())

    def left(self) -> float:
        return self.until - time.time()


def _hourly_run_going() -> bool:
    from app import worker
    return worker.run_going()


def _worker_busy() -> bool:
    from app import worker
    return worker.busy()


def run(command: list[str], minutes: float, holder: str | None = None) -> int:
    """The command under the lease, after the hourly run is over and the worker has finished its step; its exit
    status"""
    while _hourly_run_going() or held() is not None:
        time.sleep(30)
    with Hold(holder or ' '.join(command)[:120], minutes) as h:
        if _worker_busy():  # it starts no new step now, but the one it's on may hold Gemma on the card (Oct 9: R1 ran
            print('gpu_lease: waiting for the worker to finish its step', flush=True)  # out of memory beside it)
        while _worker_busy() and h.left() > 0:
            time.sleep(15)
        proc = subprocess.Popen(command)
        while proc.poll() is None:
            if h.left() <= 0:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                print(f'gpu_lease: {minutes:g} minutes up, the command stopped', flush=True)
                return 124
            time.sleep(5)
        return proc.returncode


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m app.gpu_lease')
    sub = p.add_subparsers(dest='what', required=True)
    r = sub.add_parser('run', help='run a command holding the lease')
    r.add_argument('--minutes', type=float, default=45)
    r.add_argument('--holder')
    r.add_argument('command', nargs=argparse.REMAINDER)
    sub.add_parser('status')
    sub.add_parser('release', help="drop the lease, whoever holds it")
    a = p.parse_args(argv)
    if a.what == 'status':
        lease = held()
        print('free' if lease is None else f"held by {lease['holder']} since {lease['since']}, until "
              f"{dt.fromtimestamp(lease['until']).strftime('%H:%M')}")
        return 0
    if a.what == 'release':
        release()
        return 0
    command = a.command[1:] if a.command[:1] == ['--'] else a.command
    return run(command, a.minutes, a.holder)


if __name__ == '__main__':
    sys.exit(main())
