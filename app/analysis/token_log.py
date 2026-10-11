"""How many tokens our local models read and write, by job (Oct 11: before renting compute for the archive
experiments, the person wanted to know what our work would really cost per token, not an upper bound). Every Ollama
chat call through app/analysis/llm.py, and the judge's own Gemma call, adds a line to a file for its day in DIR:
when, the job (the module or script that asked), the model, tokens read and written, seconds. Days older than KEEP
are dropped.

Report: python -m app.analysis.token_log [days]: per job and model, the calls and tokens a day, and what they'd cost
at the per-token prices in PRICES (OpenRouter's providers for Gemma 4 26B on Oct 11, cheapest and Google's own)."""
import os
import sys
from collections import defaultdict
from datetime import datetime as dt
from datetime import timedelta as td

from app.utils import Config, get_logger

logger = get_logger(__name__)

DIR = os.path.join(Config.data, 'llm_tokens')  # one CSV a day: at,job,model,prompt,output,seconds
KEEP = 30  # days
PRICES = {'gemma4:26b': {'DeepInfra': (0.07, 0.34), 'Google': (0.15, 0.60)}}  # USD per million tokens in, out
_HERE = {os.path.abspath(__file__), os.path.abspath(os.path.join(os.path.dirname(__file__), 'llm.py'))}
_pruned = set()


def job() -> str:
    """The module or script that asked: the first frame outside this file and llm.py. Under llm.parallel() that's
    the caller's own function, run in a worker thread"""
    f = sys._getframe(1)
    while f is not None:
        path = os.path.abspath(f.f_code.co_filename)
        if path not in _HERE and 'concurrent' not in path and 'threading' not in path:
            return os.path.splitext(os.path.basename(path))[0]
        f = f.f_back
    return 'unknown'


def record(model: str, answer: dict, seconds: float):
    """A line for one call: `answer` is Ollama's response (prompt_eval_count, eval_count). Never raises: the log must
    not cost a call its answer"""
    try:
        os.makedirs(DIR, exist_ok=True)
        day = dt.now().strftime('%Y-%m-%d')
        line = (f"{dt.now().isoformat(timespec='seconds')},{job()},{model},{int(answer.get('prompt_eval_count') or 0)},"
                f"{int(answer.get('eval_count') or 0)},{seconds:.2f}\n")
        with open(os.path.join(DIR, f'{day}.csv'), 'a') as f:  # one short append: whole lines between processes
            f.write(line)
        if day not in _pruned:
            _pruned.add(day)
            old = (dt.now() - td(days=KEEP)).strftime('%Y-%m-%d')
            for name in os.listdir(DIR):
                if name.endswith('.csv') and name[:10] < old:
                    os.remove(os.path.join(DIR, name))
    except Exception as e:  # noqa: BLE001
        logger.debug("Token log: %s", e)


def load(days: int = 7) -> list[tuple]:
    """[(day, job, model, prompt, output, seconds)] for the last `days` days"""
    since = (dt.now() - td(days=days)).strftime('%Y-%m-%d')
    rows = []
    for name in sorted(os.listdir(DIR)) if os.path.isdir(DIR) else []:
        if not name.endswith('.csv') or name[:10] < since:
            continue
        with open(os.path.join(DIR, name)) as f:
            for line in f:
                p = line.rstrip('\n').split(',')
                if len(p) == 6:
                    rows.append((name[:10], p[1], p[2], int(p[3]), int(p[4]), float(p[5])))
    return rows


def report(days: int = 7) -> str:
    rows = load(days)
    if not rows:
        return f'No token log yet ({DIR})'
    n_days = len({r[0] for r in rows})
    by = defaultdict(lambda: [0, 0, 0, 0.0])
    for _, j, m, p, o, s in rows:
        b = by[(m, j)]
        b[0] += 1
        b[1] += p
        b[2] += o
        b[3] += s
    out = [f'Tokens a day over {n_days} day{"s" if n_days > 1 else ""} logged (from {min(r[0] for r in rows)}):',
           f'{"model":<14} {"job":<22} {"calls":>7} {"read":>9} {"written":>9} {"hours":>6}']
    for (m, j), (c, p, o, s) in sorted(by.items(), key=lambda kv: -kv[1][1]):
        out.append(f'{m:<14} {j:<22} {c / n_days:>7.0f} {p / n_days / 1e6:>8.2f}M {o / n_days / 1e6:>8.3f}M '
                   f'{s / n_days / 3600:>6.1f}')
    for m, prices in PRICES.items():
        p = sum(v[1] for (mm, _), v in by.items() if mm == m) / n_days / 1e6
        o = sum(v[2] for (mm, _), v in by.items() if mm == m) / n_days / 1e6
        costs = ', '.join(f'{name} ${p * a + o * b:.2f}' for name, (a, b) in prices.items())
        out.append(f'\n{m} a day: {p:.2f}M read, {o:.3f}M written; at per-token prices: {costs}')
    return '\n'.join(out)


if __name__ == '__main__':
    print(report(int(sys.argv[1]) if len(sys.argv) > 1 else 7))
