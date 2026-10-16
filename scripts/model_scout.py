"""The model scout (Oct 16; the person: "we should periodically search for newest models so we keep up to date"). Once a
week it looks at what's new and lists the models worth a test here, beside what we run:

    Ollama's library, newest first                     decision models (Nimble's kind: the confidence model's judge),
                                                       embedders (the shortlist's finders), and language models that
                                                       fit the card (the filing model, the claim writer)
    Hugging Face, trending, by task                    text generation, embeddings, rerankers, classifiers

A model counts when it fits this machine (at most FITS billion parameters, or a mixture of experts whose name says so)
and is one of the kinds we use. Polite: one request a source, PAUSE seconds apart, once a week. Nothing is downloaded:
a candidate is tested only after the person says yes (the jury, J1, is how: on their own decisions, against what runs).

    ~/maudlin-data/model_scout.json    every model seen and when first seen (so only the new are reported)
    ~/Repos/maudlin-notes/model-scout.md   the week's new candidates, newest week first

    python scripts/model_scout.py         look now (deploy/systemd/user/maudlin-model-scout.timer: Mondays)"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime as dt, timedelta as td

import requests as rq
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils import Config  # noqa: E402

STATE = os.path.join(Config.data, 'model_scout.json')
NOTES = os.path.expanduser('~/Repos/maudlin-notes/model-scout.md')
AGENT = 'maudlin model scout (a personal research project; weekly)'
PAUSE = 15  # seconds between requests
FIRST_OLLAMA, FIRST_DAYS = 40, 45  # the first look lists Ollama's 40 newest and Hugging Face's last 45 days
FITS = 35  # billion parameters at most (the RTX 3080's 10 GB plus RAM, as Gemma 26B runs)
OLLAMA = 'https://ollama.com/library?sort=newest'
HF = 'https://huggingface.co/api/models'
HF_TASKS = {'text-generation': 'language model', 'feature-extraction': 'embedder', 'sentence-similarity': 'embedder',
            'text-classification': 'classifier or reranker'}
KINDS = {'decision': "a decision model, Nimble's kind: a juror for the confidence model's judge",
         'embedding': 'an embedder: a finder for the shortlist (E11 tested twelve)',
         'language model': 'a language model: the filing model, claim writer or namer, if it beats Gemma 26B',
         'classifier or reranker': 'a classifier or reranker: beside the Qwen3 reranker',
         'embedder': 'an embedder: a finder for the shortlist (E11 tested twelve)'}


def size_of(text: str) -> float | None:
    """Billions of parameters from a name or tag ('27b', '24B-A2B', '0.8b'), the largest mentioned"""
    found = [float(x) for x in re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)\s*[bB](?![a-z])', text)]
    return max(found) if found else None


def fits(size: float | None) -> bool:
    return size is None or size <= FITS


def ollama_models(html: str) -> list[dict]:
    """The library page's models: name, what it is, its kinds (decision, embedding, thinking...) and sizes"""
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for a in soup.select('a[href^="/library/"]'):
        name = a.select_one('span.truncate') or a.find('h2')
        if not name:
            continue
        spans = [s.get_text(strip=True) for s in a.select('span.inline-flex')]
        sizes = [s for s in spans if re.fullmatch(r'[\d.]+[bmBM](?:-a[\d.]+b)?|e\d+b', s.lower())]
        caps = [s for s in spans if s not in sizes]
        desc = a.find('p')
        updated = re.search(r'Updated ([^\n]+?ago)', a.get_text(' ', strip=True))
        out.append({'source': 'ollama', 'id': name.get_text(strip=True), 'about': desc.get_text(strip=True) if desc else '',
                    'kinds': caps, 'sizes': sizes, 'updated': updated.group(1) if updated else '',
                    'url': 'https://ollama.com' + a['href']})
    return out


def kind_of(m: dict) -> str | None:
    if m['source'] == 'ollama':
        caps = {c.lower() for c in m['kinds']}
        if 'cloud' in caps and not m['sizes']:  # served by Ollama's cloud only: nothing to run here
            return None
        if 'decision' in caps or 'decision model' in m.get('about', '').lower():  # pplx-decider, d1: said, not tagged
            return 'decision'
        if 'embedding' in caps:
            return 'embedding'
        return 'language model' if m['sizes'] or 'thinking' in caps or 'tools' in caps else None
    return 'embedding' if m.get('task') == 'embedder' else m.get('task')


def biggest(m: dict) -> float | None:
    if m.get('params'):
        return m['params']
    sizes = [size_of(s) for s in m.get('sizes', [])] + [size_of(m['id'])]
    sizes = [s for s in sizes if s is not None]
    return min(sizes) if sizes else None  # the smallest tag is the one that could run here


def look() -> list[dict]:
    """Every candidate the sources list now"""
    found = []
    r = rq.get(OLLAMA, headers={'User-Agent': AGENT}, timeout=60)
    r.raise_for_status()
    found += ollama_models(r.text)
    for task, kind in HF_TASKS.items():
        time.sleep(PAUSE)
        r = rq.get(HF, params={'sort': 'trendingScore', 'direction': -1, 'limit': 40, 'pipeline_tag': task,
                               'expand[]': ['safetensors', 'createdAt', 'likes', 'downloads']},
                   headers={'User-Agent': AGENT}, timeout=60)
        r.raise_for_status()
        for m in r.json():
            total = (m.get('safetensors') or {}).get('total')
            found.append({'source': 'huggingface', 'id': m['id'], 'task': kind, 'params': total / 1e9 if total else None,
                          'created': (m.get('createdAt') or '')[:10], 'likes': m.get('likes'),
                          'downloads': m.get('downloads'), 'url': f"https://huggingface.co/{m['id']}"})
    return found


def installed() -> list[str]:
    try:
        out = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=30).stdout
        return [line.split()[0] for line in out.splitlines()[1:] if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def report(new: list[dict], have: list[str], today: str) -> str:
    lines = [f'## {today}', '']
    if not new:
        lines += ['Nothing new that fits and that we use.', '']
    for kind in ('decision', 'embedding', 'language model', 'classifier or reranker'):
        group = [m for m in new if kind_of(m) == kind]
        if not group:
            continue
        lines.append(f'**{KINDS[kind][0].upper() + KINDS[kind][1:]}**')
        for m in group:
            size = biggest(m)
            bits = [f'{size:.1f}B'.replace('.0B', 'B') if size else 'size unknown']
            if m['source'] == 'ollama':
                bits += [m['updated']] if m['updated'] else []
            else:
                bits += [f"created {m['created']}", f"{m['likes']} likes"]
            lines.append(f"- [{m['id']}]({m['url']}) ({', '.join(bits)}){': ' + m['about'] if m.get('about') else ''}")
        lines.append('')
    lines += [f"Running here: {', '.join(have) or 'unknown'}.", '']
    return '\n'.join(lines)


def main():
    state = {'seen': {}}
    if os.path.exists(STATE):
        with open(STATE) as f:
            state = json.load(f)
    today = dt.now().strftime('%Y-%m-%d')
    first = not state['seen']
    new = []
    cutoff = (dt.now() - td(days=FIRST_DAYS)).strftime('%Y-%m-%d')
    for n, m in enumerate(look()):
        key = f"{m['source']}:{m['id']}"
        if key in state['seen']:
            continue
        state['seen'][key] = today
        recent = not first or (m['source'] == 'ollama' and n < FIRST_OLLAMA) or m.get('created', '') >= cutoff
        if recent and kind_of(m) and fits(biggest(m)):  # the first look: only the newest, not the whole library
            new.append(m)
    # copies of one model (its GGUF, ONNX or CoreML builds, a quantization) once: the first listed
    base = lambda m: re.sub(r'[-_](gguf|onnx|coreml|coreai|mlx|awq|gptq|\d+bit|uncensored).*$', '', m['id'].split('/')[-1].lower())  # noqa: E731
    seen, kept = set(), []
    for m in new:
        if base(m) not in seen:
            seen.add(base(m))
            kept.append(m)
    new = kept
    with open(STATE + '.tmp', 'w') as f:
        json.dump(state, f, indent=1)
    os.replace(STATE + '.tmp', STATE)
    text = report(new, installed(), today + (' (the first look: everything listed now)' if first else ''))
    old = ''
    if os.path.exists(NOTES):
        with open(NOTES) as f:
            old = f.read()
    head = '# Model scout\n\nNew models worth a test here, each week (scripts/model_scout.py). Nothing is downloaded until you say so.\n\n'
    body = old[len(head):] if old.startswith(head) else old
    with open(NOTES, 'w') as f:
        f.write(head + text + '\n' + body)
    print(f'model scout: {len(new)} new candidates; {NOTES}', flush=True)


if __name__ == '__main__':
    main()
