"""The experiments' queue, run by a service of its own (Oct 12, the person: "please make sure our experiments keep
running"). Until now each experiment ran as a chain of shell loops started from a Claude session: a reboot, a session's
end or a sleep killed them, and their logs in /tmp went with them (the night of Oct 11-12 lost most of its run). Now
each step is a row in the catalog's database (experiments.sqlite, table queue), and maudlin-experiments.service
(deploy/systemd/user) runs them one at a time, oldest first, each after the step it waits for: under the GPU lease
(app/gpu_lease.py, which takes turns with the hourly run and the worker), its output in logs/<holder>.log beside the
experiments' data. A step that fails is tried again (the experiments resume from what they saved) up to TRIES times.
While any step is waiting or running the machine is kept awake (kde-inhibit, as the worker does).

    exp_queue.py add CODE HOLDER [--minutes N] [--no-lease] [--after ID] -- command...     a step; its id
    exp_queue.py show                                                                       the queue, newest last
    exp_queue.py run                                                                        the service's loop"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime as dt

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

ROOT = '/home/mas/Repos/maudlin2'
DB = os.path.join(harness.EXP, 'experiments.sqlite')
LOGS = os.path.join(harness.EXP, 'logs')
PY = os.path.join(ROOT, '.venv', 'bin', 'python')
TRIES = 8
POLL = 30
SCHEMA = """create table if not exists queue (id integer primary key, code text, holder text, cmd text, minutes real,
    lease integer, after integer, status text, tries integer default 0, added text, started text, finished text,
    exit integer)"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute(SCHEMA)
    return con


def now() -> str:
    return dt.now().isoformat(timespec='seconds')


def add(code: str, holder: str, cmd: list[str], minutes: float = 120, lease: bool = True, after: int | None = None) -> int:
    with connect() as con:
        cur = con.execute('insert into queue (code, holder, cmd, minutes, lease, after, status, added) values '
                          '(?, ?, ?, ?, ?, ?, ?, ?)', (code, holder, json.dumps(cmd), minutes, int(lease), after, 'waiting', now()))
        return cur.lastrowid


def show():
    from codenames import figure_of
    con = connect()
    for i, code, holder, status, tries, after, started, finished in con.execute(
            'select id, code, holder, status, tries, after, started, finished from queue order by id'):
        when = finished or started or ''
        print(f"{i:4} {figure_of(holder):34} {status:8} tries {tries}{f'  after {after}' if after else '':10} {when}")


def next_step(con: sqlite3.Connection) -> tuple | None:
    """The oldest waiting step whose step before it is done; a step after a failed one is blocked"""
    for row in con.execute('select id, holder, cmd, minutes, lease, after, tries from queue where status = ? order by id',
                           ('waiting',)).fetchall():
        after = row[5]
        if after:
            before = con.execute('select status from queue where id = ?', (after,)).fetchone()
            if before and before[0] in ('failed', 'blocked'):
                con.execute('update queue set status = ? where id = ?', ('blocked', row[0]))
                con.commit()
                continue
            if not before or before[0] != 'done':
                continue
        return row
    return None


class Awake:
    """kde-inhibit held while there's work in the queue (the worker's Awake holds it only inside a cycle)"""

    def __init__(self):
        self.proc = None

    def hold(self, on: bool):
        if on and self.proc is None:
            bus = f'/run/user/{os.getuid()}/bus'
            if os.path.exists(bus):
                self.proc = subprocess.Popen(['kde-inhibit', '--power', 'sleep', 'infinity'],
                                             env={**os.environ, 'DBUS_SESSION_BUS_ADDRESS': f'unix:path={bus}'},
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        elif not on and self.proc is not None:
            os.killpg(self.proc.pid, 15)
            self.proc.wait(timeout=10)
            self.proc = None


def run():
    os.makedirs(LOGS, exist_ok=True)
    awake = Awake()
    con = connect()
    con.execute('update queue set status = ? where status = ?', ('waiting', 'running'))  # killed mid-step: again
    con.commit()
    while True:
        pending = con.execute("select count(*) from queue where status in ('waiting', 'running')").fetchone()[0]
        awake.hold(pending > 0)
        step = next_step(con)
        if step is None:
            time.sleep(POLL)
            continue
        sid, holder, cmd, minutes, lease, _, tries = step
        cmd = json.loads(cmd)
        full = ([PY, '-m', 'app.gpu_lease', 'run', '--minutes', str(minutes), '--holder', holder, '--'] if lease else []) + cmd
        con.execute('update queue set status = ?, started = ? where id = ?', ('running', now(), sid))
        con.commit()
        with open(os.path.join(LOGS, f'{holder}.log'), 'a') as log:
            log.write(f'\n== {now()} step {sid}, try {tries + 1}: {" ".join(cmd)}\n')
            log.flush()
            code = subprocess.run(full, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        if code == 0:
            con.execute('update queue set status = ?, finished = ?, exit = 0 where id = ?', ('done', now(), sid))
        else:
            tries += 1
            con.execute('update queue set status = ?, tries = ?, exit = ? where id = ?',
                        ('failed' if tries >= TRIES else 'waiting', tries, code, sid))
            time.sleep(60)  # a step that fails at once (Ollama down) shouldn't spin
        con.commit()


def main():
    p = argparse.ArgumentParser(prog='exp_queue.py')
    sub = p.add_subparsers(dest='what', required=True)
    a = sub.add_parser('add')
    a.add_argument('code')
    a.add_argument('holder')
    a.add_argument('--minutes', type=float, default=120)
    a.add_argument('--no-lease', action='store_true')
    a.add_argument('--after', type=int)
    a.add_argument('cmd', nargs=argparse.REMAINDER)
    sub.add_parser('show')
    sub.add_parser('run')
    args = p.parse_args()
    if args.what == 'add':
        cmd = args.cmd[1:] if args.cmd[:1] == ['--'] else args.cmd
        print(add(args.code, args.holder, cmd, args.minutes, not args.no_lease, args.after))
    elif args.what == 'show':
        show()
    else:
        run()


if __name__ == '__main__':
    main()
