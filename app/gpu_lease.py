"""The GPU lease (Oct 9, the person: "an experiment mode flag that reduces the work time of the worker service, like
a semaphore"). An experiment takes the lease for a while; the worker (app/worker.py) finishes the step it's on and
starts no other until it's given back, as it waits for the hourly run. A lease always runs out (MAX_MINUTES at most,
renewed while its holder lives), so an experiment that crashes can't keep production work waiting.

    python -m app.gpu_lease run --minutes 45 -- .venv/bin/python -u scripts/experiments/x.py
    python -m app.gpu_lease status

`run` waits for the hourly run to be over first, takes the lease, waits for the worker to finish the step it's on (its
models may still fill the card), holds the lease while the command runs, renews it every minute up to
its minutes, and gives it back when the command ends (or the minutes are up: then the command is stopped). An hourly
run that starts meanwhile goes first, and the worker gets a turn every TURN minutes: the command is paused (SIGSTOP)
and goes on where it was once they're done (SIGCONT). Its models live in Ollama, not in its own process, so a paused
command holds no card memory; one that holds some itself (torch on the GPU) is stopped instead, and started again.
Until Oct 14 every command was stopped and started again at least once an hour, so a step that didn't keep its own
progress started over each time: two nights of experiments (Isis, then Rip Van Winkle) ran for nothing.

A command reaches Ollama through a gate the lease keeps (Gate: OLLAMA_HOST pointed at it). To pause, the gate lets no new
request through and waits for those under way to finish, and only then is the command frozen: on Oct 15 at 14:00 Rip
Van Winkle was frozen in the middle of a batch of embeddings, Ollama couldn't hand over the answer or unload the model,
and every call of the 16:00 hourly run timed out behind it for half an hour. A request that won't finish in DRAIN
seconds is not waited for: the command is stopped instead, and started again."""
import argparse
import fcntl
import http.client
import json
import os
import signal
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
TURN = 60  # minutes a command runs before it gives the worker its turn (production's claims come first)
OLLAMA = ('127.0.0.1', 11434)
DRAIN = 300  # seconds a pause waits for the command's requests under way to finish


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
        if getattr(self, 'lease', None) is None:
            self.take()
        return self

    def take(self):
        """Take the lease and start renewing it; RuntimeError if someone else holds it"""
        with open(LEASE + '.lock', 'w') as lock:  # looking and taking at once: two waiting at the end of the hourly
            fcntl.flock(lock, fcntl.LOCK_EX)  # run could both find it free (Oct 9)
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


def _worker_caught_up(since: float) -> bool:
    from app import worker
    return worker.caught_up(since)


def _worker_had_turn(since: float) -> bool:
    from app import worker
    return worker.had_turn(since)


class Gate:
    """A pass-through to Ollama for one command, which can be shut: shut, a new request waits at the gate (never
    reaching Ollama) until it opens again; drain() waits for the requests already through to be answered in full"""

    def __init__(self, upstream: tuple = OLLAMA):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.upstream, self.open_ = upstream, threading.Event()
        self.open_.set()
        self.active, self.lock = 0, threading.Condition()
        gate = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _pass(self):
                gate.open_.wait()
                with gate.lock:
                    gate.active += 1
                try:
                    body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                    up = http.client.HTTPConnection(*gate.upstream, timeout=None)
                    headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'connection')}
                    up.request(self.command, self.path, body=body or None, headers=headers)
                    r = up.getresponse()
                    data = r.read()  # whole, then handed on: the reply is finished with Ollama before it's passed
                    up.close()
                    self.send_response(r.status)
                    for k, v in r.getheaders():
                        if k.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                            self.send_header(k, v)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (OSError, http.client.HTTPException) as e:
                    try:
                        self.send_error(502, str(e)[:200])
                    except OSError:
                        pass
                finally:
                    with gate.lock:
                        gate.active -= 1
                        gate.lock.notify_all()

            do_GET = do_POST = do_DELETE = do_HEAD = _pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def shut(self):
        self.open_.clear()

    def open(self):
        self.open_.set()

    def drain(self, seconds: float = DRAIN) -> bool:
        """Whether every request under way was answered within `seconds`"""
        end = time.time() + seconds
        with self.lock:
            while self.active and time.time() < end:
                self.lock.wait(max(0.0, min(1.0, end - time.time())))
            return not self.active

    def close(self):
        self.open_.set()
        self.server.shutdown()
        self.server.server_close()


def _signal(proc: subprocess.Popen, sig: int):
    """`sig` to the command and everything it started (its own process group)"""
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stop(proc: subprocess.Popen):
    _signal(proc, signal.SIGCONT)  # a paused command can't act on SIGTERM
    _signal(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        _signal(proc, signal.SIGKILL)
        proc.wait()


def group_pids(pgid: int) -> list[int]:
    """The processes of a process group, from /proc"""
    out = []
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                with open(f'/proc/{d}/stat') as f:
                    stat = f.read()
                if int(stat[stat.rindex(')') + 2:].split()[2]) == pgid:  # after the name: state, ppid, pgrp
                    out.append(int(d))
            except (OSError, ValueError, IndexError):
                pass
    return out


def on_gpu(pids: list[int]) -> bool:
    """Whether any of these processes holds card memory itself (nvidia-smi's compute apps); True when it can't tell"""
    try:
        out = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True
    return bool({int(x) for x in out.split() if x.strip().isdigit()} & set(pids))


def run(command: list[str], minutes: float, holder: str | None = None) -> int:
    """The command under the lease, after the hourly run is over and the worker has finished its step; its exit
    status. The hourly run comes first: if one starts while the command runs, the command is paused and the lease
    given back, and once the run is over it goes on (Oct 10: an experiment held the card through the 16:00 and 17:00
    runs, whose headline judgments timed out and crashed them).
    Production's processing comes first too: the command starts once the worker has caught up (its last cycle
    found little to do) or has finished a whole cycle since the command began waiting, and every TURN minutes it's
    paused and the worker given the card for a cycle (Oct 11: an experiment's lease held from the afternoon through
    the night left a day's claims unwritten; then, waiting for a short cycle, experiments waited all morning).
    `minutes` counts the command's own running time, not the waits"""
    left = min(float(minutes), MAX_MINUTES) * 60
    gave_way = 0.0  # when the command last gave the worker its turn
    waiting = time.time()  # since when it has waited for its first turn
    proc = None  # started once; paused and resumed after (stopped and started again only if it holds card memory)
    gate = Gate()  # its way to Ollama: shut before it's paused, so nothing is left half-answered (Oct 15)
    try:
        while True:
            while True:
                while _hourly_run_going() or held() is not None or not (
                        _worker_caught_up(gave_way) or _worker_had_turn(gave_way or waiting)):
                    time.sleep(30)
                h = Hold(holder or ' '.join(command)[:120], left / 60)
                try:
                    h.take()
                    break
                except RuntimeError:  # another waiter took it first: wait for that one
                    continue
            with h:
                if _worker_busy():  # it starts no new step now, but the one it's on may hold Gemma on the card (Oct 9:
                    print('gpu_lease: waiting for the worker to finish its step', flush=True)  # R1 ran out of memory)
                while _worker_busy() and h.left() > 0:
                    time.sleep(15)
                from app.worker import Awake  # an experiment keeps the machine awake while it runs (Oct 11-12: the
                with Awake(after=0):  # night's experiments slept from 02:45; each hourly run woke it and put it back)
                    began = time.time()
                    if proc is None:  # its own group, paused as one; its Ollama through the gate
                        proc = subprocess.Popen(command, start_new_session=True, env={**os.environ, 'OLLAMA_HOST': gate.url})
                    else:
                        _signal(proc, signal.SIGCONT)
                        print('gpu_lease: going on where it was', flush=True)
                    gate.open()
                    why = None
                    while proc.poll() is None:
                        if h.left() <= 0:
                            _stop(proc)
                            print(f'gpu_lease: {minutes:g} minutes up, the command stopped', flush=True)
                            return 124
                        if _hourly_run_going():
                            why = 'the hourly run started'
                            break
                        if time.time() - began >= TURN * 60:
                            why = f'{TURN} minutes run; the worker gets its turn'
                            break
                        time.sleep(5)
                    else:
                        return proc.returncode
                    gate.shut()  # no new request reaches Ollama; those under way are answered first
                    if on_gpu(group_pids(proc.pid)):
                        _stop(proc)
                        proc = None
                        print(f'gpu_lease: {why}; the command holds card memory, so it was stopped, to start again '
                              'after', flush=True)
                    elif not gate.drain():
                        _stop(proc)
                        proc = None
                        print(f'gpu_lease: {why}; a request to Ollama was still under way after {DRAIN} s, so the '
                              'command was stopped, to start again after', flush=True)
                    else:
                        _signal(proc, signal.SIGSTOP)
                        print(f'gpu_lease: {why}; the command paused, to go on after', flush=True)
                left -= time.time() - began
                gave_way = time.time()
            if left <= 0:
                if proc is not None:
                    _stop(proc)
                return 124
    finally:
        if proc is not None and proc.poll() is None:  # killed or interrupted itself: nothing left paused behind it
            _stop(proc)
        gate.close()


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
