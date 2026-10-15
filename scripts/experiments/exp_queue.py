"""The experiments' queue, run by a service of its own (Oct 12, the person: "please make sure our experiments keep
running"). Until now each experiment ran as a chain of shell loops started from a Claude session: a reboot, a session's
end or a sleep killed them, and their logs in /tmp went with them (the night of Oct 11-12 lost most of its run). Now
each step is a row in the catalog's database (experiments.sqlite, table queue), and maudlin-experiments.service
(deploy/systemd/user) runs them one at a time, oldest first, each after the step it waits for: under the GPU lease
(app/gpu_lease.py, which takes turns with the hourly run and the worker), its output in logs/<holder>.log beside the
experiments' data. While any step is waiting or running the machine is kept awake (kde-inhibit, as the worker does).

Since Oct 14, after two nights lost (Isis, then Rip Van Winkle, each started over at every hourly run and never
finished, and nobody knew until morning): the lease pauses a step for the hourly run and the worker's turns, rather
than stopping it, so it goes on where it was. And the queue watches each try:
- a step that crashes is tried again up to TRIES times, then 'failed';
- a step whose minutes run out goes to the back of the queue (others take their turn), and if two tries in a row
  printed no progress line it hadn't printed before (a counter, "file: 450/1951"), it's 'stuck': set aside;
- a failed or stuck step is flagged in ALERTS, which the Stream Deck's GPU key (app/deck.py) shows, until it's tried
  again (`exp_queue.py retry ID`) or done.

    exp_queue.py add CODE HOLDER [--minutes N] [--no-lease] [--after ID] [--priority P] -- command...   a step
    exp_queue.py show                                                                       the queue, newest last
    exp_queue.py retry ID [--minutes N]                                                     a failed or stuck step again
    exp_queue.py run                                                                        the service's loop"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime as dt

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
import lab_data  # noqa: E402

ROOT = '/home/mas/Repos/maudlin2'
DB = os.path.join(harness.EXP, 'experiments.sqlite')
LOGS = os.path.join(harness.EXP, 'logs')
PY = os.path.join(ROOT, '.venv', 'bin', 'python')
TRIES = 3  # crashes before a step has failed
STALLS = 2  # tries in a row that ran out of minutes with no new progress before a step is stuck
POLL = 30
ALERTS = os.path.join(harness.EXP, 'alerts.json')  # [{'id', 'holder', 'status', 'why', 'at'}]: failed or stuck steps
PROGRESS = re.compile(r'\b\d+\s*/\s*\d+\b')  # a counter in a log line: progress
SCHEMA = """create table if not exists queue (id integer primary key, code text, holder text, cmd text, minutes real,
    lease integer, after integer, status text, tries integer default 0, added text, started text, finished text,
    exit integer, priority integer default 0)"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute(SCHEMA)
    have = {r[1] for r in con.execute('pragma table_info(queue)')}
    for col, kind in (('priority', 'integer default 0'), ('stalls', 'integer default 0'), ('deferred', 'text')):
        if col not in have:
            con.execute(f'alter table queue add column {col} {kind}')
    return con


def alerts() -> list[dict]:
    try:
        with open(ALERTS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def set_alert(sid: int, holder: str | None = None, status: str | None = None, why: str = ''):
    """A step's alert raised (status given) or cleared (none)"""
    out = [a for a in alerts() if a['id'] != sid]
    if status:
        out.append({'id': sid, 'holder': holder, 'status': status, 'why': why, 'at': now()})
    tmp = ALERTS + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, ALERTS)


def new_progress(before: str, during: str) -> bool:
    """Whether a try's output (`during`) has a progress line its step's earlier output (`before`) hadn't: a counter
    not seen before, the lease's own lines aside"""
    seen = {line.strip() for line in before.splitlines()}
    return any(PROGRESS.search(line) and not line.startswith('gpu_lease') and line.strip() not in seen
               for line in during.splitlines())


def verdict(code: int, tries: int, stalls: int, progressed: bool) -> tuple[str, int, int, str]:
    """(status, tries, stalls, why) after a try that exited with `code`"""
    if code == 0:
        return 'done', tries, 0, ''
    if code == 124:  # its minutes ran out: on if it got somewhere, stuck after STALLS tries that didn't
        stalls = 0 if progressed else stalls + 1
        if stalls >= STALLS:
            return 'stuck', tries, stalls, f'{stalls} tries in a row ran out of time with no new progress'
        return 'waiting', tries, stalls, ''
    tries += 1
    if tries >= TRIES:
        return 'failed', tries, stalls, f'crashed {tries} times (exit {code})'
    return 'waiting', tries, stalls, ''


def retry(sid: int, minutes: float | None = None):
    """A failed, stuck or blocked step tried afresh (and any steps after it it had blocked)"""
    with connect() as con:
        con.execute('update queue set status = ?, tries = 0, stalls = 0, deferred = null where id = ?', ('waiting', sid))
        if minutes:
            con.execute('update queue set minutes = ? where id = ?', (minutes, sid))
        con.execute("update queue set status = 'waiting' where after = ? and status = 'blocked'", (sid,))
    set_alert(sid)


def now() -> str:
    return dt.now().isoformat(timespec='seconds')


def add(code: str, holder: str, cmd: list[str], minutes: float = 120, lease: bool = True, after: int | None = None,
        priority: int = 0) -> int:
    with connect() as con:
        cur = con.execute('insert into queue (code, holder, cmd, minutes, lease, after, status, added, priority) values '
                          '(?, ?, ?, ?, ?, ?, ?, ?, ?)',
                          (code, holder, json.dumps(cmd), minutes, int(lease), after, 'waiting', now(), priority))
        return cur.lastrowid


def prioritize(sid: int, priority: int):
    """A step (and the steps after it) taken before those of lower priority"""
    with connect() as con:
        con.execute('update queue set priority = ? where id = ? or after = ?', (priority, sid, sid))


def show():
    from codenames import figure_of
    con = connect()
    for i, code, holder, status, tries, after, started, finished in con.execute(
            'select id, code, holder, status, tries, after, started, finished from queue order by id'):
        when = finished or started or ''
        print(f"{i:4} {figure_of(holder):34} {status:8} tries {tries}{f'  after {after}' if after else '':10} {when}")


def next_step(con: sqlite3.Connection) -> tuple | None:
    """The oldest waiting step of the highest priority whose step before it is done, a step that ran out of time
    last behind the rest (by when); a step after a failed or stuck one is blocked"""
    for row in con.execute('select id, holder, cmd, minutes, lease, after, tries from queue where status = ? '
                           "order by priority desc, coalesce(deferred, ''), id", ('waiting',)).fetchall():
        after = row[5]
        if after:
            before = con.execute('select status from queue where id = ?', (after,)).fetchone()
            if before and before[0] in ('failed', 'blocked', 'stuck'):
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
        # the step itself on the experiments' own copy of the data (lab_data.py: nothing it writes reaches
        # production's); the lease around it stays on production's, where the hourly run and the worker are
        fresh = con.execute('select started from queue where id = ?', (sid,)).fetchone()[0] is None
        cmd = ['env', f'MAUDLIN_DATA={lab_data.LAB}', 'MAUDLIN_TRACE=off'] + cmd
        full = ([PY, '-m', 'app.gpu_lease', 'run', '--minutes', str(minutes), '--holder', holder, '--'] if lease else []) + cmd
        con.execute('update queue set status = ?, started = ? where id = ?', ('running', now(), sid))
        con.commit()
        path = os.path.join(LOGS, f'{holder}.log')
        before = open(path).read() if os.path.exists(path) else ''
        with open(path, 'a') as log:
            log.write(f'\n== {now()} step {sid}, try {tries + 1}: {" ".join(cmd)}\n')
            if fresh:  # a step starting fresh gets production's data as it is now; a resumed one keeps its copy
                try:
                    log.write(f'lab_data: refreshed {lab_data.refresh()}\n')
                except Exception as e:  # noqa: BLE001 - an older copy will do; say so
                    log.write(f'lab_data: refresh failed ({e}); on the copy as it was\n')
            log.flush()
            # the reranker on the CPU, as production has it: loaded on a GPU free for a moment, it filled the card and
            # Nimble had no room (Oct 13, Isis's last try: a 500 from Ollama); a step can still ask for the GPU itself
            env = {**os.environ, 'MOTIF_RERANK_DEVICE': os.environ.get('MOTIF_RERANK_DEVICE', 'cpu'),
                   'MAUDLIN_TRACE': 'off'}  # an experiment's filings aren't the pipeline's: off the 🧠 Live page
            code = subprocess.run(full, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
        with open(path) as f:
            during = f.read()[len(before):]
        stalls = con.execute('select coalesce(stalls, 0) from queue where id = ?', (sid,)).fetchone()[0]
        status, tries, stalls, why = verdict(code, tries, stalls, new_progress(before, during))
        con.execute('update queue set status = ?, tries = ?, stalls = ?, exit = ?, finished = ?, deferred = ? '
                    'where id = ?', (status, tries, stalls, code, now() if status == 'done' else None,
                                     now() if code == 124 and status == 'waiting' else None, sid))
        con.commit()
        if status in ('failed', 'stuck'):
            set_alert(sid, holder, status, why)
        elif status == 'done':
            set_alert(sid)
        if code not in (0, 124):
            time.sleep(60)  # a step that fails at once (Ollama down) shouldn't spin


def main():
    p = argparse.ArgumentParser(prog='exp_queue.py')
    sub = p.add_subparsers(dest='what', required=True)
    a = sub.add_parser('add')
    a.add_argument('code')
    a.add_argument('holder')
    a.add_argument('--minutes', type=float, default=120)
    a.add_argument('--no-lease', action='store_true')
    a.add_argument('--after', type=int)
    a.add_argument('--priority', type=int, default=0)
    sub.add_parser('show')
    sub.add_parser('run')
    r = sub.add_parser('retry')
    r.add_argument('id', type=int)
    r.add_argument('--minutes', type=float)
    # The command is everything after '--', so options may come before or after CODE and HOLDER (Oct 12: with the
    # command as argparse's remainder, '--minutes' or '--after' after HOLDER were swallowed into the command)
    argv = sys.argv[1:]
    cmd = argv[argv.index('--') + 1:] if '--' in argv else []
    args = p.parse_args(argv[:argv.index('--')] if '--' in argv else argv)
    if args.what == 'add':
        if not cmd:
            p.error("add: the command goes after '--'")
        print(add(args.code, args.holder, cmd, args.minutes, not args.no_lease, args.after, args.priority))
    elif args.what == 'show':
        show()
    elif args.what == 'retry':
        retry(args.id, args.minutes)
    else:
        run()


if __name__ == '__main__':
    main()
