"""The llm behind story titles and news filter labels. Every use asks for JSON matching a schema, so any model that
supports structured output works. By default that's a small open model served locally by Ollama
(https://ollama.com); Claude is an alternative. With neither available, llm features log once and step aside and
the site still builds from the deterministic pipeline alone.

Choose with MAUDLIN_LLM=ollama|anthropic|none (default: ollama if its server answers, else anthropic if a key is
configured). MAUDLIN_LLM_MODEL overrides the model name for either backend."""
import json
import os
import threading

import requests as rq

from app.utils import Config, get_logger

logger = get_logger(__name__)

OLLAMA_URL = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
DEFAULT_MODELS = {
    'ollama': 'qwen3:8b',  # fits a 10GB GPU at the default 4-bit quantization; any instruct model will do
    'anthropic': 'claude-haiku-4-5',
}
TIMEOUT = 120
BIG_TIMEOUT = 600  # a bigger model, partly on the CPU, loading and answering

_backend: str | None = None
_resolved = False
_lock = threading.Lock()


def _ollama_up() -> bool:
    try:
        return rq.get(f'{OLLAMA_URL}/api/version', timeout=3).ok
    except rq.RequestException:
        return False


def backend() -> str | None:
    """The llm backend in use, or None if there isn't one. Resolved once per process; the lock keeps parallel
    callers from reading the answer before the first caller has finished working it out."""
    global _backend, _resolved
    with _lock:
        if not _resolved:
            _resolve()
            _resolved = True
    return _backend


def _resolve():
    global _backend
    choice = os.environ.get('MAUDLIN_LLM', '').lower()
    if choice == 'none':
        _backend = None
    elif choice == 'ollama' or (not choice and _ollama_up()):
        _backend = 'ollama'
    elif choice == 'anthropic' or (not choice and Config.anthropic):
        _backend = 'anthropic' if Config.anthropic else None
    if _backend is None:
        logger.warning("No llm available (no Ollama server at %s, no Anthropic key), skipping llm features",
                       OLLAMA_URL)
    else:
        logger.info("Using %s with %s for llm features", _backend, model())


def model() -> str:
    return os.environ.get('MAUDLIN_LLM_MODEL') or DEFAULT_MODELS.get(_backend or '', '')


def complete_json(prompt: str, schema: dict, max_tokens: int = 1024, model: str | None = None) -> dict | None:
    """Ask the llm for JSON matching `schema`. Returns None if there's no backend or the call fails. `model` picks
    a different local model for this call (Ollama only), e.g. a bigger one for a small, hard job."""
    which = backend()
    try:
        if which == 'ollama':
            return _ollama(prompt, schema, max_tokens, model)
        if which == 'anthropic':
            return _anthropic(prompt, schema, max_tokens)
    except Exception as e:  # noqa: BLE001 - an llm hiccup should never take down a scrape or build
        logger.error("llm call failed: %s", e)
    return None


def _ollama(prompt: str, schema: dict, max_tokens: int, name: str | None = None) -> dict | None:
    response = rq.post(f'{OLLAMA_URL}/api/chat', timeout=TIMEOUT if not name else BIG_TIMEOUT, json={
        'model': name or model(),
        'messages': [{'role': 'user', 'content': prompt}],
        'format': schema,  # ollama constrains decoding to the schema
        'think': False,  # these are quick classification and labeling jobs
        'stream': False,
        'options': {'temperature': 0, 'num_predict': max_tokens},
    })
    response.raise_for_status()
    return json.loads(response.json()['message']['content'])


_client = None


def _anthropic(prompt: str, schema: dict, max_tokens: int) -> dict | None:
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=Config.anthropic)
    response = _client.messages.create(
        model=model(),
        max_tokens=max_tokens,
        messages=[{'role': 'user', 'content': prompt}],
        output_config={'format': {'type': 'json_schema', 'schema': schema}},
    )
    if response.stop_reason != 'end_turn':
        logger.warning("llm stopped with %s", response.stop_reason)
        return None
    return json.loads(next(b.text for b in response.content if b.type == 'text'))
