"""E2 Imagined instances and E7 the layered finder (docs/filing-experiments.md). Gemma's answers cached in
maudlin-data/motifs/experiments (resumable); then scored by the harness.

E2: for each motif, eight claims people might tell that are instances of it, each about a different subject, written
from its name and note only (never its claims, so a held-out claim can't leak in). A claim scored against a motif by
its best match among them (and their mean).
E7: for each claim, its layers in plain generic words (a character type, a plot, a theory or belief, an argument, a
value at stake; none where it has none); each layer against every motif's note, and the layer that goes with the
motif's genre (Archetypes: character; Plots: plot; Theories and Beliefs: theory; Arguments: argument; Values and
Exhortations: value) as a signal of its own."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import llm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

MODEL = 'gemma4:26b'
IMAGINED = os.path.join(harness.EXP, 'imagined.json')
LAYERED = os.path.join(harness.EXP, 'layers.json')
IMAGINE = """A motif in our index of recurring shapes of story in what people say about politics and public life:

Name: {name}
What it covers: {note}

Write eight short claims people might tell or post that are instances of this motif, each one sentence, the way a \
person would say it ("X is doing Y to Z"). Make each about a completely different subject: different countries, \
fields (politics, business, sports, health, religion, entertainment, technology, local life), people and years. Same \
shape of story every time; never the same topic twice."""
IMAGINE_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "minItems": 8, "maxItems": 8,
                                                              "items": {"type": "string", "maxLength": 240}}},
                  "required": ["claims"]}
LAYERS = """A claim people are telling or arguing over:
{claim}

Describe the story it tells layer by layer, each in one plain generic sentence with kinds of people, places and things \
instead of names and dates, or "none" if it doesn't have that layer:
character: the type of person or group at the center, as its tellers see them
plot: the sequence of events it says happened or will happen
theory: the hidden cause or belief about how things work that it rests on
argument: the case it makes, or the move it makes against the other side
value: the value it says is at stake or betrayed"""
LAYER_NAMES = ['character', 'plot', 'theory', 'argument', 'value']
LAYERS_SCHEMA = {"type": "object", "properties": {n: {"type": "string", "maxLength": 240} for n in LAYER_NAMES},
                 "required": LAYER_NAMES}
GENRE_LAYER = {'Archetypes': 'character', 'Plots': 'plot', 'Theories': 'theory', 'Beliefs': 'theory',
               'Arguments': 'argument', 'Values': 'value', 'Exhortations': 'value'}


def read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write(path, d):
    with open(path + '.tmp', 'w') as f:
        json.dump(d, f)
    os.replace(path + '.tmp', path)


def ask_imagined(data):
    done = read(IMAGINED)
    for i, m in enumerate(data['ids']):
        if m in done:
            continue
        e = data['entries'][m]
        a = llm.complete_json(IMAGINE.format(name=e['name'], note=e.get('note') or '(no description yet)'), IMAGINE_SCHEMA,
                              max_tokens=900, model=MODEL)
        if a and a.get('claims'):
            done[m] = a['claims']
        if i % 20 == 0:
            write(IMAGINED, done)
            print(f'imagined {len(done)}/{len(data["ids"])}', flush=True)
    write(IMAGINED, done)
    return done


def ask_layers(data):
    done = read(LAYERED)
    for i, (k, c) in enumerate(data['claims'].items()):
        if k in done:
            continue
        a = llm.complete_json(LAYERS.format(claim=c['claim']), LAYERS_SCHEMA, max_tokens=600, model=MODEL)
        if a:
            done[k] = {n: a.get(n, 'none') for n in LAYER_NAMES}
        if i % 25 == 0:
            write(LAYERED, done)
            print(f'layers {len(done)}/{len(data["claims"])}', flush=True)
    write(LAYERED, done)
    return done


if __name__ == '__main__':
    data = harness.load()
    ids, at = data['ids'], data['at']
    imagined = ask_imagined(data)
    layers = ask_layers(data)
    vec = mr.Vectors()
    flat = [(m, c) for m, cs in imagined.items() for c in cs]
    IV = vec([c for _, c in flat])
    owner = np.array([at.get(m, -1) for m, _ in flat])
    notes = vec([data['entries'][m].get('note') or data['entries'][m]['name'] for m in ids])
    genre_layer = [GENRE_LAYER.get(mi.genre_of(data['entries'][m]) or '') for m in ids]
    vec(list(dict.fromkeys(t for ls in layers.values() for t in ls.values() if t and t.strip().lower() != 'none')))  # in one go
    vec([c['claim'] for c in data['claims'].values()])

    def imagined_best(d, k):
        sims = IV @ vec([d['claims'][k]['claim']])[0]
        out = np.full(len(ids), -1.0)
        np.maximum.at(out, owner[owner >= 0], sims[owner >= 0])
        return out

    def imagined_mean(d, k):
        sims = IV @ vec([d['claims'][k]['claim']])[0]
        tot, cnt = np.zeros(len(ids)), np.zeros(len(ids))
        np.add.at(tot, owner[owner >= 0], sims[owner >= 0])
        np.add.at(cnt, owner[owner >= 0], 1)
        return np.where(cnt > 0, tot / np.maximum(cnt, 1), -1.0)

    def layer_sims(k):
        ls = layers.get(k) or {}
        return {n: (notes @ vec([ls[n]])[0] if ls.get(n) and ls[n].strip().lower() != 'none' else np.full(len(ids), -1.0))
                for n in LAYER_NAMES}

    def layers_best(d, k):
        return np.max(np.stack(list(layer_sims(k).values())), 0)

    def layers_genre(d, k):
        s = layer_sims(k)
        return np.array([s[g][i] if g else -1.0 for i, g in enumerate(genre_layer)])

    harness.evaluate(data, {'imagined best': imagined_best, 'imagined mean': imagined_mean}, label='E2 imagined instances')
    harness.evaluate(data, {'layers best': layers_best, 'layer of its genre': layers_genre}, label='E7 layered finder')
    harness.evaluate(data, {'imagined best': imagined_best, 'imagined mean': imagined_mean, 'layers best': layers_best,
                            'layer of its genre': layers_genre}, label='E2+E7 together')
    print('DONE', flush=True)
