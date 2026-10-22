"""Gaming mode (Oct 22, the person: "i need a gaming mode"): the card and the machine to the person, the project's own
GPU work held back until it's turned off.

While it's on:
- the worker starts no step and exits to give the card back (app/worker.py yielding; systemd starts it again, and it
  waits without the card);
- an experiment under the GPU lease is paused, as for the hourly run, and none starts (app/gpu_lease.py);
- the hourly run is skipped (scripts/run.sh): it asks the language model too, and its scrapers drive a browser; the
  site catches up at the first run after;
- the models Ollama holds are let go of the card when it's turned on, and after an hourly run that was under way.

It turns itself off after MAX_HOURS, so a forgotten one can't hold the project back for days.

    python -m app.gaming on [hours]     (default: until turned off, at most MAX_HOURS)
    python -m app.gaming off
    python -m app.gaming toggle
    python -m app.gaming status         (exit 0 when on: scripts/run.sh asks this way)"""
import json
import os
import sys
import time
from datetime import datetime as dt

from app.utils import Config

FLAG = os.path.join(Config.data, 'gaming.json')  # {'since', 'until'}
MAX_HOURS = 12
OLLAMA = 'http://127.0.0.1:11434'


def active() -> dict | None:
    """The gaming mode in force, or None (off, or past its time)"""
    try:
        with open(FLAG) as f:
            on = json.load(f)
    except (OSError, ValueError):
        return None
    if on.get('until', 0) < time.time():
        return None
    return on


def turn_on(hours: float | None = None) -> dict:
    hours = min(float(hours), MAX_HOURS) if hours else MAX_HOURS
    now = time.time()
    on = {'since': now, 'until': now + hours * 3600, 'at': dt.now().isoformat(timespec='seconds')}
    tmp = FLAG + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(on, f)
    os.replace(tmp, FLAG)
    on['freed'] = free_card()
    return on


def turn_off() -> bool:
    """Off; whether it was on"""
    was = active() is not None
    try:
        os.remove(FLAG)
    except FileNotFoundError:
        pass
    return was


def free_card(after_run: bool = False) -> list[str]:
    """Ask Ollama to let go of every model it holds on the card, unless the hourly run is using them (it finishes
    first; scripts/run.sh frees them after, with `after_run`): the models let go"""
    import requests
    from app import worker
    if worker.run_going() and not after_run:
        return []
    try:
        loaded = [m['name'] for m in requests.get(f'{OLLAMA}/api/ps', timeout=5).json().get('models', [])]
    except (requests.RequestException, ValueError):
        return []
    freed = []
    for name in loaded:
        try:
            requests.post(f'{OLLAMA}/api/generate', json={'model': name, 'keep_alive': 0}, timeout=30)
            freed.append(name)
        except requests.RequestException:
            pass
    return freed


def describe(on: dict | None) -> str:
    if not on:
        return 'Gaming mode is off: the machine works for bignews.day as usual.'
    left = (on['until'] - time.time()) / 3600
    return (f"🎮 Gaming mode is on since {dt.fromtimestamp(on['since']):%H:%M}: the worker, experiments and hourly runs "
            f"wait. It turns itself off in {left:.1f} h at the latest.")


def main(argv: list[str]) -> int:
    what = argv[0] if argv else 'status'
    if what == 'toggle':
        what = 'off' if active() else 'on'
    if what == 'on':
        on = turn_on(float(argv[1]) if len(argv) > 1 else None)
        freed = on.get('freed')
        print(describe(on) + (f" Let go of {', '.join(freed)}." if freed else ''))
        notify('🎮 Gaming mode on', 'The worker, experiments and hourly runs wait until you turn it off.')
        return 0
    if what == 'off':
        print('Gaming mode off: the machine goes back to work.' if turn_off() else 'Gaming mode was already off.')
        notify('🎮 Gaming mode off', 'The worker picks up where it left off; the next hourly run catches the site up.')
        return 0
    if what == 'free':  # scripts/run.sh, at the end of a run that was under way when gaming mode came on
        if active():
            free_card(after_run=True)
        return 0
    if what == 'status':
        on = active()
        print(describe(on))
        return 0 if on else 1
    print(__doc__)
    return 2


def notify(title: str, body: str):
    """A desktop notification, when there's a desktop to show it (the launcher's only feedback)"""
    import shutil
    import subprocess
    if shutil.which('notify-send') and os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        subprocess.run(['notify-send', '-a', 'bignews.day', title, body], check=False, timeout=5)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
