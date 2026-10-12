"""app/analysis/reranker_teach.py: which reranker scores come from (cached apart), and when teaching is due."""
import json
from datetime import datetime as dt, timedelta as td

from app.analysis import reranker_teach as rt


def test_the_tag_names_the_taught_reranker_and_teaching_waits_a_week_and_new_decisions(monkeypatch, tmp_path):
    monkeypatch.setattr(rt, 'TAUGHT', str(tmp_path / 'taught.pt'))
    monkeypatch.setattr(rt, 'META', str(tmp_path / 'taught.json'))
    assert rt.tag() == 'base' and rt.due()  # never taught
    (tmp_path / 'taught.pt').write_bytes(b'x')
    week_ago = (dt.now() - td(days=8)).isoformat(timespec='seconds')
    (tmp_path / 'taught.json').write_text(json.dumps({'at': week_ago, 'decisions': 700}))
    assert rt.tag() == week_ago
    monkeypatch.setattr(rt.fc, 'decisions', lambda *a, **k: dict.fromkeys(range(720)))
    assert not rt.due()  # a week, but only 20 new decisions
    monkeypatch.setattr(rt.fc, 'decisions', lambda *a, **k: dict.fromkeys(range(760)))
    assert rt.due()
    (tmp_path / 'taught.json').write_text(json.dumps({'at': dt.now().isoformat(timespec='seconds'), 'decisions': 0}))
    assert not rt.due()  # taught today


def test_nothing_taught_leaves_the_base_model_as_it_is(monkeypatch, tmp_path):
    monkeypatch.setattr(rt, 'TAUGHT', str(tmp_path / 'none.pt'))
    model = object()
    assert rt.load_into(model) is model


def _teaching(monkeypatch, tmp_path, taught_right: bool):
    """teach() with the models and the index faked: the fold models score the decisions well or badly, the untaught
    reranker in between"""
    import types
    monkeypatch.setattr(rt, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(rt, 'TAUGHT', str(tmp_path / 'taught.pt'))
    monkeypatch.setattr(rt, 'META', str(tmp_path / 'taught.json'))
    monkeypatch.setattr(rt, 'HELD_OUT', str(tmp_path / 'held_out.json'))
    rows = [(f'claim {i}', 'M1', i % 2 == 0, 'decision') for i in range(12)] + [('claim x', 'M1', True, 'truth')]
    monkeypatch.setattr(rt.mi, 'load', dict)
    monkeypatch.setattr(rt, 'examples', lambda index: rows)
    sig = types.SimpleNamespace(at={'M1': 0}, _document=lambda n, ex: 'doc', nearest_claims=lambda c, n, lo, k: [])
    monkeypatch.setattr(rt.ms, 'Signals', lambda index: sig)
    tok = types.SimpleNamespace(convert_tokens_to_ids=lambda t: t)
    model = types.SimpleNamespace(eval=lambda: None, named_parameters=list)
    monkeypatch.setattr(rt, '_model', lambda: (tok, types.SimpleNamespace(kind='base', **vars(model))))
    monkeypatch.setattr(rt, '_train', lambda rs, texts, seed: (tok, types.SimpleNamespace(kind='taught', **vars(model)),
                                                               'yes', 'no'))

    def score(tok, model, yes, no, rs, texts):
        out = {}
        for i, (c, e, ok, _) in enumerate(rs):
            if model.kind == 'base':  # right two times in three
                p = (0.8 if ok else 0.2) if i % 3 else (0.2 if ok else 0.8)
            else:
                p = (0.9 if ok else 0.1) if taught_right else (0.1 if ok else 0.9)
            out[f'{rt.mi.key(c)}|{e}'] = p
        return out
    monkeypatch.setattr(rt, '_score', score)
    rt.teach()
    return json.loads((tmp_path / 'taught.json').read_text())


def test_a_teaching_keeps_the_taught_reranker_only_if_it_judges_better_than_the_untaught(monkeypatch, tmp_path):
    meta = _teaching(monkeypatch, tmp_path, taught_right=True)
    assert meta['kept'] == 'taught' and meta['taught_auc'] > meta['base_auc'] and meta['decisions'] == 12
    assert (tmp_path / 'taught.pt').exists() and (tmp_path / 'held_out.json').exists()
    assert rt.tag() == meta['at']
    meta = _teaching(monkeypatch, tmp_path, taught_right=False)  # the next week's teaching judges worse
    assert meta['kept'] == 'base' and meta['taught_auc'] < meta['base_auc']
    assert not (tmp_path / 'taught.pt').exists()  # the earlier taught layers go too
    assert rt.tag() == 'base'
