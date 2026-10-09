"""Pipelining the language model (Oct 8, the person: "if we can pipeline this stuff so we're not idling"): Gemma 4 26B
doesn't fit the 10 GB card, so Ollama keeps most of its experts in system memory and the CPU does part of every token
while the GPU waits; Ollama runs 4 requests at once (OLLAMA_NUM_PARALLEL=4), but the pipeline asks one at a time.
Timed here: the same kinds of request one at a time and four at a time, on real inputs (different ones each way, so
no prompt is cached): the shape rewrite (short), the layers (medium) and a show transcript part (long)."""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/mas/Repos/maudlin2')
sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from app.analysis import llm, motif_index as mi, motif_signals as ms, show_claims  # noqa: E402

N = int(os.environ.get('N', 12))


def timed(calls, workers):
    t = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = list(pool.map(lambda f: f(), calls))
    took = time.time() - t
    return took, sum(1 for g in got if g)


def main():
    llm.backend()
    claims = [c['claim'] for e in mi.live(mi.load()) for c in e['claims']][::7][:4 * N]
    eps = show_claims.episodes()
    chunks = [(ep, ch) for ep in eps for ch in ep['chunks']][:N // 2 * 2]
    kinds = {
        'shape (short)': [lambda c=c: llm.complete_json(ms.SHAPE_PROMPT.format(claim=c), ms.SHAPE_SCHEMA, max_tokens=200,
                                                         model=ms.JUDGE_MODEL) for c in claims[:2 * N]],
        'layers (medium)': [lambda c=c: llm.complete_json(ms.LAYERS_PROMPT.format(claim=c), ms.LAYERS_SCHEMA, max_tokens=600,
                                                           model=ms.JUDGE_MODEL) for c in claims[2 * N:4 * N]],
        'show part (long)': [lambda ep=ep, ch=ch: llm.complete_json(
            show_claims.PROMPT.format(show=ep['show'], kind=ep['kind'], title=ep['title'], text=ch['text']),
            show_claims.SCHEMA, max_tokens=1000, model=show_claims.MODEL) for ep, ch in chunks],
    }
    llm.complete_json(ms.SHAPE_PROMPT.format(claim='warm up'), ms.SHAPE_SCHEMA, max_tokens=20, model=ms.JUDGE_MODEL)
    for name, calls in kinds.items():
        half = len(calls) // 2
        one, ok1 = timed(calls[:half], 1)
        four, ok4 = timed(calls[half:], 4)
        line = (f"LLM pipelining, {name}: one at a time {one / half:.1f} s a request, four at a time {four / half:.1f} s "
                f"({one / four:.2f}x the work per second; {ok1}+{ok4} of {2 * half} answered)")
        print(line, flush=True)
        harness.note(line)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
