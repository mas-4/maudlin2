"""Speech-to-text bake-off (Oct 8, the person: "check 'em out!"): today's Whisper (faster-whisper large-v3-turbo)
against NVIDIA's Parakeet TDT 0.6B v3 and Qwen3-ASR 1.7B, on the first CLIP seconds of real episodes from shows that
publish their own transcripts (sidefeeds.TRANSCRIPTS), the published text as the reference.

The published transcripts are machines' too (mostly iHeart's), so the word error rate is disagreement with another
machine, not with the truth: fair for comparing the three, not a score of any. Measured too: speed (seconds of audio
per second of work), the card's memory, and the share of the reference's capitalized words (names, mostly) each
gets: a claim hinges on who it names. Each model on the GPU alone (the language model unloaded first)."""
import json
import os
import re
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app import transcribe  # noqa: E402

CLIP = 600  # seconds of each episode
CHUNK = 60  # seconds per piece for the two transformers models
SHOWS = ['breakingpoints', 'jessekelly', 'bloombergnow']  # a panel, a call-in, a newscast
OUT = os.path.join(harness.EXP, 'asr_bakeoff.json')


def episodes() -> list[dict]:
    """The newest episode with a published transcript of a panel show, a call-in show and a newscast, read from their
    feeds (one request each)"""
    import requests

    from app import sidefeeds
    out = []
    for key in SHOWS:
        src = sidefeeds.BY_KEY[key]
        items = sidefeeds.parse(requests.get(src['url'], timeout=60, headers={'User-Agent': sidefeeds.USER_AGENT}).text)
        it = next((i for i in items if i.get('transcript') and i.get('audio')), None)
        if it:
            out.append({'show': src['name'], 'title': it['title'], 'audio': it['audio'], 'transcript': it['transcript']})
        time.sleep(2)
    return out


def words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", ' ', text.lower().replace('’', "'")).split()


def wer(ref: list[str], hyp: list[str]) -> float:
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / max(1, len(ref))


def names(text: str) -> set[str]:
    """Capitalized words not starting a sentence: names, mostly"""
    out = set()
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b", text):
        out.add(m.group(1).lower())
    return out - {'the', 'and', 'but', 'that', 'this', 'what', 'they', 'well', 'yeah'}


def whisper(audio: np.ndarray) -> str:
    segments, _ = transcribe.model().transcribe(audio, language='en', vad_filter=True, beam_size=1)
    return ' '.join(s.text.strip() for s in segments)


def parakeet(audio: np.ndarray) -> str:
    import torch
    from transformers import AutoModelForTDT, AutoProcessor
    global _parakeet
    if '_parakeet' not in globals():
        proc = AutoProcessor.from_pretrained('nvidia/parakeet-tdt-0.6b-v3')
        model = AutoModelForTDT.from_pretrained('nvidia/parakeet-tdt-0.6b-v3', dtype=torch.float16).to('cuda').eval()
        _parakeet = (proc, model)
    proc, model = _parakeet
    out = []
    for i in range(0, len(audio), CHUNK * 16000):
        inputs = proc([audio[i:i + CHUNK * 16000]], sampling_rate=16000).to('cuda', dtype=torch.float16)
        with torch.no_grad():
            got = model.generate(**inputs, return_dict_in_generate=True)
        text = proc.decode(got.sequences, skip_special_tokens=True)
        out.append(text[0] if isinstance(text, list) else text)
    return ' '.join(out)


def qwen(audio: np.ndarray) -> str:
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor
    global _qwen
    if '_qwen' not in globals():
        proc = AutoProcessor.from_pretrained('Qwen/Qwen3-ASR-1.7B-hf')
        model = AutoModelForMultimodalLM.from_pretrained('Qwen/Qwen3-ASR-1.7B-hf', dtype=torch.bfloat16).to('cuda').eval()
        _qwen = (proc, model)
    proc, model = _qwen
    out = []
    for i in range(0, len(audio), CHUNK * 16000):
        inputs = proc.apply_transcription_request(audio=audio[i:i + CHUNK * 16000], language='English').to(model.device, model.dtype)
        with torch.no_grad():
            ids = model.generate(**inputs, max_new_tokens=600)
        out.append(proc.decode(ids[:, inputs['input_ids'].shape[1]:], return_format='transcription_only')[0])
    return ' '.join(out)


MODELS = {'whisper large-v3-turbo (today)': whisper, 'parakeet tdt 0.6b v3': parakeet, 'qwen3-asr 1.7b': qwen}


def main():
    import requests
    import torch
    transcribe.free_gpu()
    eps = episodes()
    print(f'{len(eps)} episodes:', [e['show'] for e in eps], flush=True)
    clips = []
    with tempfile.TemporaryDirectory(prefix='asr-bakeoff-') as folder:
        for e in eps:
            path = transcribe.download(e['audio'], folder)
            audio = transcribe.decode(path)[:CLIP * 16000]
            ref_segments = transcribe.parse_timed(requests.get(e['transcript'], timeout=60,
                                                               headers={'User-Agent': transcribe.USER_AGENT}).text)
            ref = ' '.join(s['text'] for s in ref_segments if s['start'] < len(audio) / 16000)
            clips.append({**e, 'audio_np': audio, 'ref': ref, 'seconds': len(audio) / 16000})
            time.sleep(2)
    results = {}
    for name, fn in MODELS.items():
        transcribe.free_gpu()  # anything that loaded the language model again meanwhile
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        fn(clips[0]['audio_np'][:16000 * 5])  # load the model (not timed)
        rows = []
        for c in clips:
            t = time.time()
            hyp = fn(c['audio_np'])
            took = time.time() - t
            ref_names = names(c['ref'])
            got = set(words(hyp))
            rows.append({'show': c['show'], 'seconds': c['seconds'], 'took': round(took, 1),
                         'wer': round(wer(words(c['ref']), words(hyp)), 3),
                         'names': round(len(ref_names & got) / max(1, len(ref_names)), 3), 'n names': len(ref_names),
                         'sample': hyp[:400]})
            print(f"{name} | {c['show']}: {took:.0f} s for {c['seconds']:.0f} s, disagreement {rows[-1]['wer']:.1%}, "
                  f"names {rows[-1]['names']:.0%} of {len(ref_names)}", flush=True)
        audio = sum(r['seconds'] for r in rows)
        results[name] = {'rows': rows, 'speed': round(audio / sum(r['took'] for r in rows), 1),
                         'wer': round(sum(r['wer'] * r['seconds'] for r in rows) / audio, 3),
                         'names': round(sum(r['names'] * r['n names'] for r in rows) / max(1, sum(r['n names'] for r in rows)), 3),
                         'gpu GB': round(torch.cuda.max_memory_allocated() / 1e9, 2)}
        line = (f"ASR bake-off, {name}: {results[name]['speed']}x real time, disagreement with the shows' own transcripts "
                f"{results[name]['wer']:.1%}, their names {results[name]['names']:.0%}, card {results[name]['gpu GB']} GB (torch)")
        print(line, flush=True)
        harness.note(line)
        if name != 'whisper large-v3-turbo (today)':  # free the card for the next
            globals().pop('_parakeet' if 'parakeet' in name else '_qwen', None)
    with open(OUT, 'w') as f:
        json.dump({'refs': [{'show': c['show'], 'title': c['title'], 'ref': c['ref'][:600]} for c in clips], 'results': results},
                  f, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
