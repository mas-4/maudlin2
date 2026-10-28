"""scripts/experiments/o1_wolf.py (the Wolf in Sheep's Clothing, Oct 28): the barbell test tells a bell with a separate
tail from one bell slid toward heat, the agreement measures and the gate, and the paper's sections."""
import sqlite3
import sys

import numpy as np
import pytest

sys.path.insert(0, 'scripts/experiments')
import o1_wolf as w  # noqa: E402

CUTS = w.cuts_of([np.log(1.0), np.log(1.0), np.log(1.0)])  # 0, 1, 2, 3


def draw(p, n, seed=0):
    return np.random.default_rng(seed).multinomial(n, p).astype(float)


def test_a_bell_at_straight_with_a_separate_tail_is_found_and_its_share_recovered():
    p = w.mixture(-1.0, 0.04, CUTS, 0.4)
    mu, share, ll1 = w.fit_mixture(draw(p / p.sum(), 4000), CUTS, 0.4)
    _, ll0 = w.fit_bell(draw(p / p.sum(), 4000), CUTS)
    assert share == pytest.approx(0.04, abs=0.012)
    assert mu == pytest.approx(-1.0, abs=0.15)
    assert w.lr_p(2 * (ll1 - ll0)) < 1e-6


def test_one_bell_slid_toward_heat_gets_no_tail():
    p = w.bell(1.2, CUTS)
    c = draw(p / p.sum(), 4000, seed=1)
    _, share, ll1 = w.fit_mixture(c, CUTS, 0.4)
    _, ll0 = w.fit_bell(c, CUTS)
    assert share < 0.01
    assert w.lr_p(2 * (ll1 - ll0)) > 0.05


def test_the_shared_shape_comes_back_from_outlets_at_different_centres():
    cuts = w.cuts_of([np.log(0.7), np.log(1.2), np.log(0.9)])
    table = {f'o{i}': draw(w.bell(mu, cuts) / w.bell(mu, cuts).sum(), 3000, seed=i)
             for i, mu in enumerate([-1.0, -0.3, 0.4, 1.0, 1.8, 2.5])}
    got, q = w.fit_shape(table)
    assert got == pytest.approx(cuts, abs=0.12)
    assert 0 < q < 1


def test_analyse_calls_a_barbell_a_barbell_and_a_wire_one_shifted_mode():
    cuts = w.cuts_of([np.log(0.9), np.log(0.9), np.log(0.9)])
    rng = np.random.default_rng(3)

    def outlet(p, n):
        slants = rng.choice(5, size=n, p=p / p.sum())
        return [{'kind': 'report', 'slant': int(s), 'side': 'right' if s else 'none'} for s in slants]
    labelled = {f'plain{i}': outlet(w.bell(mu, cuts), 600) for i, mu in enumerate([-1.6, -1.2, -0.9, -0.5])}
    labelled['hot'] = outlet(w.bell(1.0, cuts), 600)
    labelled['wolf'] = outlet(w.mixture(-1.5, 0.06, cuts, 0.4), 600)
    labelled['thin'] = outlet(w.bell(-1.0, cuts), 40)
    rows, shape = w.analyse(labelled, boots=60)
    by = {r['outlet']: r for r in rows}
    assert by['wolf']['verdict'] == 'barbell'
    assert by['wolf']['w_lo'] > 0
    assert by['plain0']['verdict'] in ('one shifted mode', "can't tell")
    assert by['hot']['verdict'].startswith('heat')
    assert by['thin']['verdict'] == 'too few' and 'w' not in by['thin']
    assert set(shape) == {'c2', 'c3', 'c4', 'q'}


def test_verdicts():
    base = {'n': 300, 'w': 0.03, 'w_lo': 0.01, 'w_hi': 0.05, 'p_holm': 0.001, 'bell_mode': 0}
    assert w.verdict(base) == 'barbell'
    assert w.verdict({**base, 'p_holm': 0.2}) == "can't tell"
    assert w.verdict({**base, 'w': 0.002, 'w_lo': 0, 'w_hi': 0.006, 'p_holm': 0.5}) == 'one shifted mode'
    assert w.verdict({**base, 'bell_mode': 2}) == 'heat with a tail'
    assert w.verdict({**base, 'bell_mode': 1, 'p_holm': 0.5}) == 'heat'
    assert w.verdict({**base, 'n': 20}) == 'too few'
    assert w.verdict({**base, 'w': 0.005, 'w_lo': 0.002}) == "can't tell"  # real but too small to matter


def test_holm_and_the_valley():
    assert w.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert w.valley([0.8, 0.1, 0.03, 0.02, 0.05]) == pytest.approx(0.03)
    assert w.valley([0.6, 0.25, 0.1, 0.04, 0.01]) == 0
    assert w.lr_p(0) == 1.0


def test_kappa_and_the_gate():
    assert w.kappa(['a', 'b', 'a', 'b'], ['a', 'b', 'a', 'b']) == pytest.approx(1)
    assert w.kappa([0, 1, 2, 3, 4], [0, 1, 2, 3, 4], 'quadratic', levels=list(range(5))) == pytest.approx(1)
    assert w.kappa([0, 0, 4, 4], [0, 1, 3, 4], 'quadratic', levels=list(range(5))) > w.kappa(
        [0, 0, 4, 4], [4, 4, 0, 0], 'quadratic', levels=list(range(5)))
    same = [({'kind': k, 'slant': s, 'side': 'none'},) * 2 for k, s in
            [('report', 0), ('report', 1), ('opinion', 3), ('other', 0), ('report', 4), ('opinion', 2)]]
    a = w.agreement(same)
    assert a['kind_accuracy'] == 1 and a['tail_kappa'] == pytest.approx(1) and w.gate_passes(a)
    off = [(h, {**m, 'slant': 4 - m['slant']}) for h, m in same]
    assert not w.gate_passes(w.agreement(off))


def test_round_robin_covers_every_outlet_evenly_and_caps_it():
    got = w.round_robin({'a': list(range(10)), 'b': list(range(100, 103))}, cap=5)
    assert len(got) == 8
    assert [o for o, _, _ in got[:4]] == ['a', 'b', 'a', 'b']
    assert sorted(h for o, h, _ in got if o == 'b') == [100, 101, 102]
    assert got == w.round_robin({'b': list(range(100, 103)), 'a': list(range(10))}, cap=5)


def test_the_paper_section_is_replaced_between_its_markers_and_nothing_else():
    text = 'head\n<!-- wolf:results -->\nto come\n<!-- /wolf:results -->\ntail'
    out = w.replace_section(text, 'results', 'the numbers')
    assert out == 'head\n<!-- wolf:results -->\nthe numbers\n<!-- /wolf:results -->\ntail'
    assert w.replace_section(out, 'results', 'again').count('wolf:results') == 2
    with pytest.raises(ValueError):
        w.replace_section(text, 'validation', 'x')


def test_the_prompt_hides_the_outlet_and_asks_only_for_the_headline():
    assert '{agency}' not in w.PROMPT and '{title}' in w.PROMPT
    assert w.SCHEMA['required'].index('note') < w.SCHEMA['required'].index('slant')


def _connect(path):
    con = sqlite3.connect(path)
    con.executescript(w.SCHEMA_SQL)
    return con


def _fake_model(monkeypatch, answer):
    from app.analysis import llm
    monkeypatch.setattr(w, 'ask', answer)
    monkeypatch.setattr(llm, 'parallel', lambda fn, items, workers=4: [fn(i) for i in items])


def _paper(tmp_path, monkeypatch) -> str:
    db, paper = str(tmp_path / 'o1.sqlite'), str(tmp_path / 'paper.md')
    with open(paper, 'w') as f:
        f.write('# P\n<!-- wolf:validation -->\nnot yet\n<!-- /wolf:validation -->\n'
                '<!-- wolf:results -->\nnot yet\n<!-- /wolf:results -->\n')
    monkeypatch.setattr(w, 'PAPER', paper)
    monkeypatch.setattr(w, 'connect', lambda path=db: _connect(path))
    monkeypatch.setattr(w, 'new_run', lambda con, stage, notes='': _run(con, stage, notes))
    return paper


_ticks = iter(range(10 ** 6))


def _run(con, stage, notes):
    rid = f'O1:{stage}:{next(_ticks):06d}'
    con.execute('insert into runs values (?, ?, ?, ?, ?, ?, ?)', (rid, stage, rid, '', w.MODEL, w.PROMPT_ID, notes))
    return rid


def _sample(con, rows):
    con.execute("insert into runs values ('O1:sample:0', 'sample', '0', '', 'm', 'p', ?)",
                ('{"since": "2026-09-28", "until": "2026-10-28", "cap": 400, "outlets": ["AP"]}',))
    con.executemany("insert into headlines values (?, 'O1:sample:0', ?, ?, ?, '', ?)",
                    [(h, h, o, t, r) for h, o, t, r in rows])


def test_trial_label_and_report_run_end_to_end_on_a_fake_model(tmp_path, monkeypatch):
    """The queued steps in order, a fake model in place of Gemma: the gate, the reading, the paper filled"""
    paper = _paper(tmp_path, monkeypatch)
    monkeypatch.setattr(w, 'BOOTS', 20)
    rng = np.random.default_rng(5)
    shape = {'AP': w.bell(-1.5, CUTS), 'Reuters': w.bell(-1.4, CUTS), 'One America News Network':
             w.mixture(-1.4, 0.06, CUTS, 0.4), 'Breitbart': w.bell(1.2, CUTS), 'Newsmax': w.bell(-0.8, CUTS)}
    truth, rows = {}, []
    for o, p in shape.items():
        for i in range(220):
            hid = len(rows) + 1
            truth[f't{hid}'] = int(rng.choice(5, p=p / p.sum()))
            rows.append((hid, o, f't{hid}', i))
    con = w.connect()
    _sample(con, rows)
    con.executemany("insert into hand values (?, ?, ?, 'report', ?, 'none', 'claude', '')",
                    [(h, o, t, truth[t]) for h, o, t, _ in rows[::11]])
    con.commit()
    _fake_model(monkeypatch, lambda title: {'kind': 'report', 'note': '', 'slant': truth[title], 'side': 'right',
                                            'seconds': 0.1})
    w.trial()
    assert 'The gate passed' in open(paper).read()
    w.label()
    assert w.connect().execute('select count(*) from labels').fetchone()[0] == len(rows)
    w.report()
    text = open(paper).read()
    assert 'not yet' not in text
    assert '| One America News Network |' in text and 'Against the hypotheses' in text
    assert w.connect().execute("select verdict from results where variant = 'all' and outlet = 'Breitbart'"
                               ).fetchone()[0].startswith('heat')


def test_a_failed_gate_stops_the_reading_and_says_so(tmp_path, monkeypatch):
    paper = _paper(tmp_path, monkeypatch)
    con = w.connect()
    _sample(con, [(h, 'AP', f't{h}', 0) for h in range(40)])
    con.executemany("insert into hand values (?, 'AP', ?, 'report', ?, 'none', 'claude', '')",
                    [(h, f't{h}', h % 5) for h in range(40)])
    con.commit()
    _fake_model(monkeypatch, lambda title: {'kind': 'opinion', 'note': '', 'slant': 4 - int(title[1:]) % 5,
                                            'side': 'left', 'seconds': 0.1})
    w.trial()
    w.label()
    assert w.connect().execute('select count(*) from labels').fetchone()[0] == 40  # the hand sample's only
    w.report()
    text = open(paper).read()
    assert 'The gate failed' in text and 'gate failed on the hand sample' in text
