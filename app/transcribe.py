"""Transcribe podcast audio from the shows archive (app/sidefeeds.py) on our own GPU with Whisper (faster-whisper,
large-v3-turbo): nothing leaves the machine. It runs after each hourly build, when the language model is idle,
working newest-first through a priority list (the hourly newscasts first) within a time budget. Audio is downloaded,
transcribed and deleted; the text is kept, with the model that made it, for analysis only (never republished).

A 5-minute NPR newscast takes about 3 seconds on an RTX 3080 (about 90x real time), so a day of every archived
show is a few minutes of GPU time."""
import ctypes
import glob
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime as dt, timedelta as td
from typing import Optional

import numpy as np
import pytz
import requests as rq

from app.models import Session, SqlLock, SideItem, SideTranscript
from app.utils import Config, Constants, get_logger

logger = get_logger(__name__)

MODEL = 'large-v3-turbo'
COMPUTE = 'int8_float16'
JUDGE = f'faster-whisper {MODEL} {COMPUTE}'
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
MAX_BYTES = 250 * 1024 * 1024  # skip anything bigger (multi-hour streams)
RECENT = td(days=3)  # only items this new; no backfilling the archive's history
# Hourly newscasts first, then the shows on the site, then the rest
PRIORITY = ['nprnewsnow', 'abcupdate']
OLLAMA = 'http://localhost:11434'
PAUSE = 2  # seconds between downloads
# Sponsor reads at the start or end of an episode ("This message comes from…")
AD = re.compile(r'\b(?:this (?:message|episode|podcast) (?:comes|is brought|is sponsored)|support (?:for|comes from)'
                r"|sponsored by|what's in your wallet|terms apply|promo code|learn more at)\b", re.IGNORECASE)

_model = None


# Names and terms Whisper mishears in political talk ("APEC" for AIPAC, "Hexeth" for Hegseth), given to it as hotwords
# on every stretch of audio, with the people most named in recent stories (entities); and the mishearings fixed after
# transcription, each only where it's safe (APEC is also the Asia-Pacific summit; "a PAC" is a political action committee)
TERMS = ['AIPAC', 'DOGE', 'MSNOW', 'MAGA', 'SCOTUS', 'Hegseth', 'Whatley', 'Ramaswamy', 'El-Sayed', 'Tallarico',
         'Ossoff', 'Houthis', 'Hezbollah', 'Netanyahu', 'Zelensky', 'Bolsonaro', 'Epstein', 'Fairford', 'ICE']
HOTWORD_NAMES = 50  # the most-named people and groups in recent stories added to TERMS
FIXES = [
    (re.compile(r'\bAPAC\b'), 'AIPAC', None),
    (re.compile(r'\bAPEC\b'), 'AIPAC', re.compile(r'summit|Asia|Pacific|trade|economic cooperation|ministers|Korea|leaders\' meeting', re.I)),
    (re.compile(r'\b(?:Hexeth|Heggseth|Hegsath|Hexath)\b'), 'Hegseth', None),
    (re.compile(r'\bWattley\b'), 'Whatley', None),
]


def hotwords() -> str:
    """The terms Whisper should expect: TERMS and the most-named people and groups in recent stories"""
    try:
        from app.analysis import entities
        names = [n for n, _ in sorted(entities.all_names().items(), key=lambda kv: -kv[1])
                 if n[:1].isupper()][:HOTWORD_NAMES]
    except Exception:  # noqa: the fixed terms alone will do
        names = []
    return ', '.join(dict.fromkeys(TERMS + names))


def fix_text(text: str) -> str:
    """Known mishearings corrected, sentence by sentence: a fix with a guard isn't made in a sentence the guard
    matches (APEC the summit stays APEC)"""
    out = []
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        for pattern, right, guard in FIXES:
            if guard is None or not guard.search(sentence):
                sentence = pattern.sub(right, sentence)
        out.append(sentence)
    return ' '.join(out)


def _load_cuda_libs():
    """ctranslate2 looks up cuBLAS and cuDNN when it first runs; the pip-installed copies live in the venv, which
    the dynamic linker doesn't search, so load them by full path first (they then satisfy its lookups)."""
    root = os.path.join(Constants.Paths.ROOT, '.venv', 'lib', 'python*', 'site-packages', 'nvidia')
    for pattern in ('cuda_nvrtc/lib/libnvrtc.so*', 'cublas/lib/libcublasLt.so*', 'cublas/lib/libcublas.so*',
                    'cudnn/lib/libcudnn*.so*'):
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            try:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def model():
    global _model
    if _model is None:
        _load_cuda_libs()
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL, device='cuda', compute_type=COMPUTE)
    return _model


def free_gpu(wait: float = 30) -> bool:
    """Ask Ollama to unload its model so Whisper has the GPU's memory (the next run loads it again), and wait until
    it has. False if something keeps it loaded (another job using the language model)."""
    deadline = time.time() + wait
    while True:
        try:
            loaded = rq.get(f'{OLLAMA}/api/ps', timeout=5).json().get('models', [])
        except Exception:  # noqa: no Ollama running means nothing to free
            return True
        if not loaded:
            return True
        if time.time() > deadline:
            return False
        for m in loaded:
            try:
                rq.post(f'{OLLAMA}/api/generate', json={'model': m['name'], 'keep_alive': 0}, timeout=30)
            except Exception:  # noqa
                pass
        time.sleep(2)


def permanent(error: Exception) -> bool:
    """Whether an error will happen again on retry (the file is gone or unreadable), as opposed to something passing
    (the GPU out of memory, a network blip), which should just wait for the next run."""
    text = str(error).lower()
    if 'out of memory' in text or 'cuda' in text or isinstance(error, (rq.ConnectionError, rq.Timeout)):
        return False
    status = getattr(getattr(error, 'response', None), 'status_code', None)
    return status in (404, 410) or isinstance(error, subprocess.CalledProcessError)


def decode(path: str) -> np.ndarray:
    """Audio as 16 kHz mono floats, decoded by ffmpeg."""
    raw = subprocess.run(['ffmpeg', '-nostdin', '-i', path, '-f', 's16le', '-ac', '1', '-ar', '16000',
                          '-loglevel', 'error', '-'], capture_output=True, check=True, timeout=600).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def trim_ads(segments: list[dict], window: float = 45) -> list[dict]:
    """Drop sponsor reads at the start and the end: everything up to the last ad-like line in the first `window`
    seconds, and everything from the first ad-like line in the last `window` seconds. Mid-roll ads stay (rare in
    newscasts; shows can be handled later)."""
    if not segments:
        return segments
    total = segments[-1]['end']
    start = max((n + 1 for n, seg in enumerate(segments) if seg['start'] < window and AD.search(seg['text'])),
                default=0)
    end = min((n for n, seg in enumerate(segments) if seg['end'] > total - window and n >= start
               and AD.search(seg['text'])), default=len(segments))
    return segments[start:end]


def download(url: str, folder: str) -> Optional[str]:
    path = os.path.join(folder, 'audio')
    with rq.get(url, headers={'User-Agent': USER_AGENT}, timeout=Config.timeout, stream=True) as response:
        response.raise_for_status()
        size = 0
        with open(path, 'wb') as f:
            for chunk in response.iter_content(1 << 16):
                size += len(chunk)
                if size > MAX_BYTES:
                    return None
                f.write(chunk)
    return path


def pending(limit: int = 50) -> list[SideItem]:
    """Untranscribed recent items with audio, hourly newscasts first, then shows on the site, then call-ins and
    focus groups, newest first."""
    from app import sidefeeds
    published = {s['key'] for s in sidefeeds.SOURCES if s['publish']}
    since = dt.now(pytz.UTC).replace(tzinfo=None) - RECENT
    with Session() as s:
        done = s.query(SideTranscript.item_id)
        rows = s.query(SideItem).filter(SideItem.audio.isnot(None), SideItem.published >= since,
                                        SideItem.id.notin_(done)).all()
        s.expunge_all()

    voices = {s['key'] for s in sidefeeds.SOURCES if s['kind'] == 'call-in'} | {'focusgroup'}

    def rank(item):
        # Hourly newscasts, then shows on the site, then ordinary people's voices (call-ins, focus groups), then the
        # rest of the archive (long talk shows and streams)
        tier = (0 if item.source in PRIORITY else 1 if item.source in published else 2 if item.source in voices
                else 3)
        return tier, -item.published.timestamp()
    return sorted(rows, key=rank)[:limit]


def transcribe_pending(budget: float = 600) -> int:
    """Transcribe pending items until the time budget (seconds) runs out; returns how many were done."""
    items = pending()
    if not items:
        return 0
    if not free_gpu():
        logger.info("Transcribe: the language model is busy; trying next run")
        return 0
    started, done = time.time(), 0
    words = hotwords()
    for item in items:
        if time.time() - started > budget:
            break
        try:
            with tempfile.TemporaryDirectory(prefix='maudlin-audio-') as folder:
                path = download(item.audio, folder)
                if path is None:
                    logger.info("Transcribe: %s too big, skipped", item.title)
                    save(item.id, [], 0, model='skipped: over the size limit')  # so it isn't downloaded again
                    continue
                audio = decode(path)
            segments, info = model().transcribe(audio, language='en', vad_filter=True, beam_size=1, hotwords=words)
            kept = trim_ads([{'start': round(s.start, 1), 'end': round(s.end, 1), 'text': fix_text(s.text.strip())}
                             for s in segments])
            save(item.id, kept, len(audio) / 16000)
            done += 1
        except Exception as e:  # noqa: one bad file mustn't stop the rest
            if permanent(e):
                logger.warning("Transcribe: %s failed for good (%s)", item.title, e)
                save(item.id, [], 0, model=f'failed: {type(e).__name__}'[:64])  # recorded, not retried every hour
            else:
                logger.warning("Transcribe: %s failed for now (%s); stopping until next run", item.title, e)
                break  # out of memory or offline: the rest would fail the same way
        time.sleep(PAUSE)
    logger.info("Transcribed %d of %d pending items in %.0fs", done, len(items), time.time() - started)
    return done


def save(item_id: int, segments: list[dict], seconds: float, model: str = JUDGE):
    """Store a transcript, or a record that an item was skipped or failed (so it isn't downloaded again; delete
    the row to retry it)."""
    with Session() as s, SqlLock:
        s.add(SideTranscript(item_id=item_id, model=model, created=dt.now(pytz.UTC).replace(tzinfo=None),
                             seconds=seconds, text=' '.join(seg['text'] for seg in segments),
                             segments=json.dumps(segments)))
        s.commit()
