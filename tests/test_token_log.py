"""app/analysis/token_log.py: each model call's tokens logged by the job that asked, old days dropped"""
import os

from app.analysis import llm, token_log


def ask_from_a_job(monkeypatch):
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {'message': {'content': '{"ok": true}'}, 'prompt_eval_count': 1500, 'eval_count': 40}
    monkeypatch.setattr(llm.rq, 'post', lambda *a, **k: R())
    return llm._ollama('a prompt', {}, 64, name='gemma4:26b')


def test_a_call_is_logged_under_the_job_that_asked_and_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(token_log, 'DIR', str(tmp_path / 'tokens'))
    assert ask_from_a_job(monkeypatch) == {'ok': True}
    assert llm.parallel(lambda _: ask_from_a_job(monkeypatch), [1, 2], workers=2) == [{'ok': True}] * 2
    (day,) = os.listdir(tmp_path / 'tokens')
    lines = (tmp_path / 'tokens' / day).read_text().splitlines()
    assert len(lines) == 3 and all(',test_token_log,gemma4:26b,1500,40,' in ln for ln in lines)
    text = token_log.report()
    assert 'test_token_log' in text and 'DeepInfra $0.00' in text


def test_old_days_are_dropped_and_a_broken_log_costs_no_answer(monkeypatch, tmp_path):
    d = tmp_path / 'tokens'
    d.mkdir()
    (d / '2020-01-01.csv').write_text('x\n')
    monkeypatch.setattr(token_log, 'DIR', str(d))
    monkeypatch.setattr(token_log, '_pruned', set())
    ask_from_a_job(monkeypatch)
    assert '2020-01-01.csv' not in os.listdir(d)
    monkeypatch.setattr(token_log, 'DIR', '/proc/no/such/place')
    assert ask_from_a_job(monkeypatch) == {'ok': True}
