"""Build AutoTrust's GEV-26B-Decide for Ollama (Oct 8, for the jury: J1). GEV is Gemma 4 26B (the model we run) with a
LoRA on its attention and dense MLP and a decision head: 24 rows read off the last hidden state, one for each answer
word (false, true, 0-5, A-P). Ollama has no place for an adapter plus a head, so: the LoRA merged into the weights
(W + alpha/r * B @ A), and the head written into an output layer of its own (Gemma ties it to the input embeddings),
its 24 rows in place of those words' rows; llama.cpp's Gemma 4 reads an output layer when there is one. The head's
bias and calibration temperature are left out: for a yes or no, both only shift and scale the true-false difference,
so any ranking of filings (the jury's AUC) is unchanged.

Steps (each skipped when its output exists): merge into MERGED (safetensors, a layer's worth per shard, so memory
stays small), convert to a bf16 GGUF with llama.cpp's converter (the lm_head kept, as output.weight), then
`ollama create gev-26b-decide --quantize q4_K_M`. CPU only, at low priority."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

from safetensors import safe_open
from safetensors.torch import save_file

SRC = glob.glob(os.path.expanduser('~/.cache/huggingface/hub/models--autotrust--GEV-26B-Decide/snapshots/*'))[0]
WORK = '/home/mas/maudlin-data/models'
MERGED = os.path.join(WORK, 'gev-26b-merged')
GGUF = os.path.join(WORK, 'gev-26b-decide-bf16.gguf')
LLAMA = '/home/mas/maudlin-data/llama.cpp'
NAME = 'gev-26b-decide'
TARGET = re.compile(r'model\.language_model\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj)\.weight$')
SHARD_BYTES = 2 * 1024 ** 3


def merge():
    if os.path.exists(os.path.join(MERGED, 'model.safetensors.index.json')):
        print('merged already', flush=True)
        return
    os.makedirs(MERGED, exist_ok=True)
    cfg = json.load(open(os.path.join(SRC, 'adapter', 'adapter_config.json')))
    scale = cfg['lora_alpha'] / cfg['r']
    lora = safe_open(os.path.join(SRC, 'adapter', 'adapter_model.safetensors'), 'pt')
    lkeys = set(lora.keys())
    head = safe_open(os.path.join(SRC, 'head.safetensors'), 'pt').get_tensor('proj.weight')
    ids = json.load(open(os.path.join(SRC, 'judge_config.json')))['verbalizer_ids']
    weight_map = json.load(open(os.path.join(SRC, 'model.safetensors.index.json')))['weight_map']
    files = {}
    for name, f in weight_map.items():
        files.setdefault(f, []).append(name)
    out_map, shard, size, n, merged = {}, {}, 0, 0, 0

    def flush():
        nonlocal shard, size, n
        if shard:
            fname = f'model-{n:05d}.safetensors'
            save_file(shard, os.path.join(MERGED, fname), metadata={'format': 'pt'})
            out_map.update(dict.fromkeys(shard, fname))
            print(f'  {fname}: {len(shard)} tensors', flush=True)
            shard, size, n = {}, 0, n + 1
    for f, names in files.items():
        with safe_open(os.path.join(SRC, f), 'pt') as src:
            for name in names:
                t = src.get_tensor(name)
                if TARGET.search(name):
                    base = 'base_model.model.' + name[:-len('.weight')]
                    a, b = f'{base}.lora_A.weight', f'{base}.lora_B.weight'
                    if a in lkeys and b in lkeys:
                        t = (t.float() + scale * (lora.get_tensor(b).float() @ lora.get_tensor(a).float())).to(t.dtype)
                        merged += 1
                if name == 'model.language_model.embed_tokens.weight':
                    out = t.clone()
                    out[ids] = head.to(out.dtype)
                    shard['lm_head.weight'] = out.contiguous()
                    size += out.numel() * out.element_size()
                shard[name] = t.contiguous()
                size += t.numel() * t.element_size()
                if size >= SHARD_BYTES:
                    flush()
    flush()
    print(f'{merged} LoRA weights merged (of {len(lkeys) // 2}); head rows {len(ids)} written into lm_head', flush=True)
    json.dump({'metadata': {}, 'weight_map': out_map}, open(os.path.join(MERGED, 'model.safetensors.index.json'), 'w'))
    for x in os.listdir(SRC):
        p = os.path.join(SRC, x)
        if os.path.isfile(p) and x.endswith(('.json', '.jinja')) and not x.startswith('model.safetensors'):
            shutil.copy(p, os.path.join(MERGED, x))
    c = json.load(open(os.path.join(MERGED, 'config.json')))
    c['tie_word_embeddings'] = False
    c.setdefault('text_config', {})['tie_word_embeddings'] = False
    json.dump(c, open(os.path.join(MERGED, 'config.json'), 'w'), indent=1)


CONVERT = r'''
import sys
sys.path.insert(0, "{llama}"); sys.path.insert(0, "{llama}/gguf-py")
sys.argv = ["convert_hf_to_gguf.py", "{merged}", "--outtype", "bf16", "--outfile", "{gguf}"]
import gguf
from conversion import gemma
_orig = gemma.Gemma4Model.modify_tensors
def keep_head(self, data_torch, name, bid):
    if name in ("lm_head.weight", "model.lm_head.weight"):  # GEV's decision head: kept as an output layer of its own,
        # trimmed to the vocabulary as the input embeddings are (by going the same way, then renamed)
        for _, t in _orig(self, data_torch, "model.embed_tokens.weight", bid):
            yield (self.format_tensor_name(gguf.MODEL_TENSOR.OUTPUT), t)
        return
    yield from _orig(self, data_torch, name, bid)
gemma.Gemma4Model.modify_tensors = keep_head
import runpy
runpy.run_path("{llama}/convert_hf_to_gguf.py", run_name="__main__")
'''


def convert():
    if os.path.exists(GGUF):
        print('converted already', flush=True)
        return
    code = CONVERT.format(llama=LLAMA, merged=MERGED, gguf=GGUF + '.part')
    subprocess.run([sys.executable, '-c', code], check=True)
    os.rename(GGUF + '.part', GGUF)


def create():
    have = subprocess.run(['ollama', 'list'], capture_output=True, text=True).stdout
    if NAME in have:
        print('in Ollama already', flush=True)
        return
    modelfile = os.path.join(WORK, 'Modelfile.gev')
    with open(modelfile, 'w') as f:
        f.write(f'FROM {GGUF}\nPARAMETER temperature 0\n')
    subprocess.run(['ollama', 'create', NAME, '-f', modelfile, '--quantize', 'q4_K_M'], check=True)


if __name__ == '__main__':
    merge()
    convert()
    create()
    print('DONE', flush=True)
