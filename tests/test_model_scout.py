"""scripts/model_scout.py: sizes read from names and tags; only models that fit this machine and that we'd use"""
import sys

sys.path.insert(0, 'scripts')
import model_scout as m  # noqa: E402


def test_sizes_and_kinds():
    assert m.size_of('LFM2.5-24B-A2B') == 24 and m.size_of('Qwen3.8-27B-Uncensored') == 27 and m.size_of('gpt-x3-150m') is None
    nimble = {'source': 'ollama', 'id': 'nimble-v3', 'kinds': ['tools', 'decision'], 'sizes': ['9b'], 'updated': ''}
    cloud = {'source': 'ollama', 'id': 'mistral-large-4', 'kinds': ['cloud', 'tools'], 'sizes': [], 'updated': ''}
    big = {'source': 'huggingface', 'id': 'zai-org/GLM-5.3', 'task': 'language model', 'params': 753.3}
    assert m.kind_of(nimble) == 'decision' and m.fits(m.biggest(nimble))
    assert m.kind_of(cloud) is None  # nothing to run here
    assert not m.fits(m.biggest(big))
