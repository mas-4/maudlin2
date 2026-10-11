"""The desktop status panel (Oct 11, the person: "some kind of overlay on my desktop with information about this
stuff... statuses like the dashboard for bnd but more about computer situation what's running"). Prints a compact
plain-text panel for the Plasma widget in deploy/plasma/maudlin-status, which runs it every few seconds: the lights
and their key, the GPU, the hourly run, the worker, the GPU lease, what the work queue says is running, today's claims,
and the machine. Each part that can't be read says so and the rest still shows.

Run: python -m app.desk"""
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime as dt

from app.utils import Config

QUEUE = os.path.expanduser('~/Repos/maudlin-notes/queue.md')
DAY_HOURS = (8, 23)  # app/lights.py's DAY and NIGHT
WIDTH = 64
LOOKS = {  # app/lights.py's looks, in words
    'TEAL': 'teal breathing: the worker', 'VIOLET': 'violet flowing: an experiment', 'AMBER': 'amber flowing: the hourly run',
    'IDLE': 'blue breathing: idle', 'RED': 'red: a failed run or too hot', 'EMBER': 'ember: night, working',
    'DARK': 'dark: night, idle'}
KEY = '🟦 worker  🟪 experiment  🟧 hourly run  🔵 idle  🔴 failed/hot  🌙 23-08 dark'


def sh(*cmd, timeout=10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ''


def ago(seconds: float) -> str:
    seconds = max(0, seconds)
    if seconds < 90:
        return f'{seconds:.0f} s'
    if seconds < 5400:
        return f'{seconds / 60:.0f} min'
    return f'{seconds / 3600:.1f} h'


def lights_line() -> str:
    from app import lights
    try:
        load, temp = lights.card()
        state = {'who': lights.who(), 'load': load, 'temp': temp, 'failed': lights.failed()}
        d = dt.now()
        effect, colour, _, bright = lights.look(state, d.hour + d.minute / 60)
        name = next((n for n in LOOKS if getattr(lights, n) == colour), None)
        words = LOOKS.get(name) or f'{effect.lower()} {colour}'
        return f"💡 {words}{f', brightness {bright}/5' if bright else ''}"
    except Exception as e:  # noqa: BLE001 - the panel shows what it can
        return f'💡 lights: unreadable ({e})'[:WIDTH]


def gpu_line() -> list[str]:
    out = sh('nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw',
             '--format=csv,noheader,nounits')
    if not out:
        return ['🎛 GPU: unreadable']
    util, temp, used, total, power = [x.strip() for x in out.split(',')]
    models = [line.split()[0] for line in sh('ollama', 'ps').splitlines()[1:] if line.strip()]
    return [f'🎛 GPU {util}% · {temp}°C · {float(used) / 1024:.1f}/{float(total) / 1024:.1f} GB · {float(power):.0f} W',
            f"   loaded: {', '.join(models) or 'no model'}"]


def hourly_line() -> str:
    show = dict(line.split('=', 1) for line in sh('systemctl', 'show', 'maudlin-scrape.service', '-p', 'ActiveState',
                                                  '-p', 'Result', '-p', 'ExecMainStartTimestamp').splitlines() if '=' in line)
    timer = sh('systemctl', 'list-timers', 'maudlin-scrape.timer', '--no-legend').split()
    nxt = next((t[:5] for t in timer if re.fullmatch(r'\d\d:\d\d:\d\d', t)), '?')
    going = show.get('ActiveState') not in ('inactive', 'failed', '')
    started = show.get('ExecMainStartTimestamp', '').split()
    start = started[2][:5] if len(started) > 2 else '?'
    if going:
        return f'⏱ hourly run: going since {start}'
    result = '✅ ok' if show.get('Result') == 'success' else f"❌ {show.get('Result', '?')}"
    return f'⏱ hourly run: last {start} {result} · next {nxt}'


def worker_line() -> str:
    try:
        with open(os.path.join(Config.data, 'worker.json')) as f:
            beat = json.load(f)
    except (OSError, ValueError):
        return '🛠 worker: no heartbeat'
    if time.time() - beat.get('at', 0) > 600:
        return f"🛠 worker: down (last beat {ago(time.time() - beat.get('at', 0))} ago)"
    last = beat.get('last cycle') or {}
    tail = f" · last cycle {last.get('minutes', '?')} min at {last.get('at', '')[11:16]}" if last else ''
    if beat.get('busy'):
        return f"🛠 worker: working · {beat.get('cycles', 0)} cycles since {beat.get('since', '')[11:16]}{tail}"
    if beat.get('waiting'):
        return f"🛠 worker: waiting for {beat['waiting']}{tail}"
    return f'🛠 worker: caught up, idle{tail}'


def lease_line() -> str:
    from app import gpu_lease
    lease = gpu_lease.held()
    if lease is None:
        return '🧪 GPU lease: free'
    return f"🧪 GPU lease: {lease['holder']} until {dt.fromtimestamp(lease['until']).strftime('%H:%M')}"


def queue_lines(n: int = 4) -> list[str]:
    """The first lines of each item in the work queue's 'Running now' section"""
    try:
        with open(QUEUE) as f:
            text = f.read()
    except OSError:
        return []
    m = re.search(r'^## Running now.*?\n(.*?)(?=^## )', text, re.S | re.M)
    items = [line[2:] for line in (m.group(1).splitlines() if m else []) if line.startswith('- ')]
    out = [f'   · {re.sub(r"^\[[^]]*\] ", "", i)[:WIDTH - 5]}' for i in items[:n]]
    return ['📋 running now (queue):'] + out if out else ['📋 running now (queue): nothing listed']


def claims_line() -> str:
    try:
        with open(os.path.join(Config.data, 'motif_index.json')) as f:
            index = json.load(f)
    except (OSError, ValueError):
        return '🗂 claims: index unreadable'
    today = dt.now().strftime('%Y-%m-%d')
    dates = [c.get('date', '') for e in index.get('entries', {}).values() if not e.get('merged_into')
             for c in e.get('claims', [])]
    newest = max(dates, default='')
    return f"🗂 filings today: {sum(d.startswith(today) for d in dates)} · newest {newest or 'none'}"


def machine_line() -> str:
    with open('/proc/uptime') as f:
        up = float(f.read().split()[0])
    with open('/proc/meminfo') as f:
        mem = {k: int(v.split()[0]) for k, v in (line.split(':', 1) for line in f)}
    used = (mem['MemTotal'] - mem['MemAvailable']) / 2 ** 20
    disk = shutil.disk_usage('/')
    return (f'🖥 up {ago(up)} · RAM {used:.0f}/{mem["MemTotal"] / 2 ** 20:.0f} GB · '
            f'disk {disk.used / disk.total:.0%} ({disk.free / 2 ** 30:.0f} GB free)')


def panel() -> str:
    lines = [f"standingwater · {dt.now().strftime('%a %H:%M')}", '', lights_line(), KEY, '']
    for part in (gpu_line, hourly_line, worker_line, lease_line, claims_line, queue_lines, machine_line):
        try:
            got = part()
        except Exception as e:  # noqa: BLE001 - one part failing leaves the rest
            got = f'{part.__name__}: {e}'
        lines += got if isinstance(got, list) else [got]
    return '\n'.join(lines)


def hourly_words() -> str:
    line = hourly_line()
    if 'going since' in line:
        return 'going now, since ' + line.split('since ')[1]
    m = re.search(r'last (\S+) (.) (\S+) · next (\S+)', line)
    if not m:
        return line
    nxt = m.group(4)
    try:
        at = dt.combine(dt.now().date(), dt.strptime(nxt, '%H:%M').time())
        nxt = f'next in {max(0, (at - dt.now()).total_seconds()) / 60:.0f} min'
    except ValueError:
        nxt = f'next {nxt}'
    return f"{'ok' if m.group(3) == 'ok' else 'failed'} at {m.group(1)} · {nxt}"


def worker_words() -> str:
    line = re.sub(r'^\S+ worker: ', '', worker_line())
    return re.sub(r' · \d+ cycles since (\S+)', r' since \1', line).replace('working', 'busy')


def claims_words() -> str:
    from datetime import timedelta as td
    try:
        with open(os.path.join(Config.data, 'motif_index.json')) as f:
            index = json.load(f)
    except (OSError, ValueError):
        return 'unreadable'
    dates = [c.get('date', '') for e in index.get('entries', {}).values() if not e.get('merged_into')
             for c in e.get('claims', [])]
    today = dt.now().date()
    count = lambda day: sum(d.startswith(day.isoformat()) for d in dates)  # noqa: E731
    return f'{count(today)} today · {count(today - td(days=1))} yesterday'


def running_items() -> list[str]:
    """The work queue's 'Running now' items, each its first sentence, without the session tag"""
    try:
        with open(QUEUE) as f:
            text = f.read()
    except OSError:
        return []
    m = re.search(r'^## Running now.*?\n(.*?)(?=^## )', text, re.S | re.M)
    items, cur = [], None
    for line in (m.group(1).splitlines() if m else []):
        if line.startswith('- '):
            cur = [line[2:]]
            items.append(cur)
        elif cur is not None and line.strip():
            cur.append(line.strip())
    out = []
    for parts in items:
        text = re.sub(r'^\[[^]]*\] ', '', ' '.join(parts))
        text = re.sub(r'\s*\([^)]*\)', '', text)  # no asides
        head, _, tail = text.partition(': ')
        text = tail if tail and len(head.split()) <= 3 else text  # "chain: S1 ..." is the S1
        out.append(re.split(r'; | — |\. ', text, maxsplit=1)[0].strip())
    return out


def load_history(minutes: int = 60) -> list[dict]:
    """The last `minutes` of the GPU, a minute a point: {'v': load, 'who': who had it}, from app/lights.py's log (the
    GPU logger's load where the lights weren't running)"""
    from app import lights

    def tail(name: str) -> list[str]:
        try:
            with open(os.path.join(Config.data, name), 'rb') as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 80 * (minutes + 5)))
                return f.read().decode(errors='ignore').splitlines()[1:][-minutes:]
        except OSError:
            return []
    seen = {}
    for line in tail(lights.LOG):
        parts = line.split(',')
        if len(parts) == 3:
            seen[parts[0][:16]] = parts[1]
    out = []
    for line in tail('gpu_log.csv'):
        parts = [p.strip() for p in line.split(',')]
        try:
            when = dt.strptime(parts[0][:16], '%Y/%m/%d %H:%M').strftime('%Y-%m-%dT%H:%M')
            out.append({'v': float(parts[2].rstrip(' %')), 'who': seen.get(when, '')})
        except (IndexError, ValueError):
            continue
    return out


def data() -> dict:
    """The panel as data, for the Plasma widget to lay out (python -m app.desk --json)"""
    from app import gpu_lease, lights
    out = {'time': dt.now().strftime('%a %H:%M')}
    try:
        load, temp = lights.card()
        state = {'who': lights.who(), 'load': load, 'temp': temp, 'failed': lights.failed()}
        d = dt.now()
        effect, colour, speed, bright = lights.look(state, d.hour + d.minute / 60)
        title = {'worker': 'Writing claims and filing', 'experiment': 'Running an experiment',
                 'hourly': 'The hourly run', 'idle': 'Idle'}[state['who']]
        if state['failed']:
            title += ' · last run failed'
        out['look'] = {'title': title, 'effect': effect.lower(), 'color': '#%02x%02x%02x' % colour,
                       'brightness': bright, 'night': not DAY_HOURS[0] <= d.hour < DAY_HOURS[1]}
    except Exception as e:  # noqa: BLE001
        out['look'] = {'title': 'Lights unreadable', 'effect': 'direct', 'color': '#666666', 'brightness': 0,
                       'error': str(e)}
    g = sh('nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw',
           '--format=csv,noheader,nounits')
    if g:
        util, temp, used, total, power = [float(x) for x in g.split(',')]
        names = [line.split()[0].split(':')[0] for line in sh('ollama', 'ps').splitlines()[1:] if line.strip()]
        chat = [n for n in names if 'embed' not in n]
        embedders = len(names) - len(chat)
        models = ' · '.join(chat + ([f"{embedders} embedder{'s' if embedders > 1 else ''}"] if embedders else []))
        out['gpu'] = {'util': util, 'temp': temp, 'mem': round(used / 1024, 1), 'mem_total': round(total / 1024, 1),
                      'power': round(power), 'models': models or 'no model loaded', 'history': load_history()}
    out['rows'] = [{'name': name, 'value': value} for name, value in (
        ('Hourly run', hourly_words()), ('Worker', worker_words()), ('Claims filed', claims_words()))]
    out['running'] = running_items()
    out['machine'] = re.sub(r'^\S+ ', '', machine_line())
    out['lease'] = (gpu_lease.held() or {}).get('holder')
    return out


if __name__ == '__main__':
    import sys
    print(json.dumps(data()) if '--json' in sys.argv else panel())
