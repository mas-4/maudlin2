"""The always-on worker (Oct 9, the person: "I like all 4 changes"). The hourly run had done everything in one go
within systemd's 45 minutes: scrape, build, publish, then the GPU's work (app/processing.py). Its analysis kept
growing; five runs were stopped at the limit on Oct 8-9, and between runs the GPU sat idle. Now the hourly run
scrapes, builds and publishes (about 15 minutes), and this worker does the processing whenever the GPU is free:
it waits while the hourly run goes, then works in cycles of CYCLE seconds, each the steps of process() with their
budgets, a step not begun once the hourly run starts again, or an experiment takes the GPU lease (app/gpu_lease.py).

While it works it keeps the machine awake (kde-inhibit, as the hourly run does), so the desktop's idle timer and the
run's own back-to-sleep (scripts/run.sh) leave it be; idle, it lets the machine sleep and carries on after the wake.
It leaves a heartbeat (HEARTBEAT): while that's fresh, the hourly run leaves the processing to it; if the worker is
down, the run does it as before. It exits when its checkout has new code (the hourly run pulls), so systemd starts it
again on the new code (deploy/maudlin-worker.service, Restart=always).

Run: python -m app.worker"""
import json
import os
import subprocess
import time
from datetime import datetime as dt

from app.utils import Config, get_logger

logger = get_logger(__name__)

HEARTBEAT = os.path.join(Config.data, 'worker.json')  # {'pid', 'at', 'busy', 'commit', 'cycles', 'last cycle'}
FRESH = 10 * 60  # seconds: a heartbeat older than this means no worker
CYCLE = 30 * 60  # seconds a cycle of processing may take (its steps' budgets within it)
IDLE = 5 * 60  # seconds to wait after a cycle that found nothing much to do
BUSY_CYCLE = 90  # seconds: a cycle shorter than this found little to do
POLL = 30  # seconds between looks while the hourly run goes
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alive() -> bool:
    """A worker is up: its heartbeat is fresh"""
    try:
        with open(HEARTBEAT) as f:
            beat = json.load(f)
        return time.time() - beat['at'] < FRESH
    except (OSError, ValueError, KeyError):
        return False


def busy() -> bool:
    """A worker is in the middle of a cycle (scripts/run.sh doesn't put the machine to sleep then)"""
    try:
        with open(HEARTBEAT) as f:
            beat = json.load(f)
        return time.time() - beat['at'] < FRESH and bool(beat.get('busy'))
    except (OSError, ValueError, KeyError):
        return False


def run_going() -> bool:
    """The hourly run is going (a one-shot service is 'activating' while it runs: anything but inactive or failed)"""
    state = subprocess.run(['systemctl', 'show', '-p', 'ActiveState', '--value', 'maudlin-scrape.service'],
                           capture_output=True, text=True).stdout.strip()
    return state not in ('inactive', 'failed', '')


def yielding() -> str | None:
    """Why the worker should leave the GPU now: the hourly run going, or an experiment holding the GPU lease
    (app/gpu_lease.py); None when it's free"""
    if run_going():
        return 'the hourly run'
    from app import gpu_lease
    lease = gpu_lease.held()
    return f"an experiment ({lease['holder']})" if lease else None


def commit() -> str:
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def beat(state: dict, **changes):
    state.update(pid=os.getpid(), at=time.time())
    state.update(changes)
    tmp = HEARTBEAT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f)
    os.replace(tmp, HEARTBEAT)


class Awake:
    """Keep the machine from sleeping while inside (kde-inhibit over the session bus, as scripts/run.sh does);
    without the bus or kde-inhibit, nothing"""

    def __enter__(self):
        self.proc = None
        bus = f'/run/user/{os.getuid()}/bus'
        if os.path.exists(bus) and subprocess.run(['which', 'kde-inhibit'], capture_output=True).returncode == 0:
            self.proc = subprocess.Popen(['kde-inhibit', '--power', 'sleep', 'infinity'],
                                         env={**os.environ, 'DBUS_SESSION_BUS_ADDRESS': f'unix:path={bus}'},
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return self

    def __exit__(self, *exc):
        if self.proc is not None:
            os.killpg(self.proc.pid, 15)
            self.proc.wait(timeout=10)


def cycle(state: dict) -> float:
    """One cycle of processing; its seconds. The heartbeat goes on every minute meanwhile (a cycle can take half an
    hour; the hourly run would otherwise think the worker gone and process too)"""
    import threading
    from app import processing
    started = time.time()
    beat(state, busy=True)
    done = threading.Event()

    def keep_beating():
        while not done.wait(60):
            beat(state, busy=True)
    beating = threading.Thread(target=keep_beating, daemon=True)
    beating.start()
    try:
        with Awake():
            processing.process(limit=CYCLE, stop=lambda: yielding() is not None)
    except Exception as e:  # noqa: BLE001 - one bad cycle mustn't stop the worker; the next one tries again
        logger.exception("Worker: the cycle failed (%s)", e)
    finally:
        done.set()
        beating.join()
    took = time.time() - started
    beat(state, busy=False, cycles=state.get('cycles', 0) + 1,
         **{'last cycle': {'at': dt.now().isoformat(timespec='seconds'), 'minutes': round(took / 60, 1)}})
    logger.info("Worker: a cycle in %.1f minutes", took / 60)
    return took


def main():
    start = commit()
    state = {'commit': start[:7], 'cycles': 0, 'since': dt.now().isoformat(timespec='seconds')}
    logger.info("Worker up at %s", start[:7])
    while True:
        if commit() != start:
            logger.info("Worker: new code; exiting so systemd starts it again on it")
            beat(state, busy=False, at=0)  # not fresh: the hourly run processes until the new worker beats
            return
        if (why := yielding()):
            beat(state, busy=False, waiting=why)
            time.sleep(POLL)
            continue
        state.pop('waiting', None)
        took = cycle(state)
        if took < BUSY_CYCLE:  # caught up: look again in a while, beating meanwhile
            for _ in range(IDLE // POLL):
                beat(state, busy=False)
                if yielding():
                    break
                time.sleep(POLL)


if __name__ == '__main__':
    main()
