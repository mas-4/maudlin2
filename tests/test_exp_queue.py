"""scripts/experiments/exp_queue.py (Oct 14, after two nights lost): a crash is tried TRIES times; a step whose minutes
run out goes behind the others, and is stuck after STALLS such tries with no new progress; failed and stuck steps are
flagged until tried again."""
import sys

sys.path.insert(0, 'scripts/experiments')
import exp_queue as q  # noqa: E402


def test_a_try_that_got_somewhere_goes_on_and_one_that_didnt_gets_stuck():
    assert q.verdict(0, 0, 1, False)[0] == 'done'
    assert q.verdict(124, 0, 0, True)[:3] == ('waiting', 0, 0)  # out of time, but further on: again, later
    assert q.verdict(124, 0, 0, False)[:3] == ('waiting', 0, 1)
    status, _, stalls, why = q.verdict(124, 0, 1, False)
    assert status == 'stuck' and stalls == 2 and 'no new progress' in why
    assert q.verdict(1, 1, 0, False)[:2] == ('waiting', 2)
    assert q.verdict(1, 2, 0, False)[0] == 'failed'  # the third crash


def test_progress_is_a_counter_not_seen_before():
    before = 'Using ollama\nfile: 0/1951\nfile: 50/1951\n'
    assert q.new_progress(before, 'Using ollama\nfile: 100/1951\n')
    assert not q.new_progress(before, 'Using ollama\nfile: 50/1951\ngpu_lease: 120/240 minutes\n')  # nothing new
    assert not q.new_progress('', 'Loading weights\nReranker on cpu\n')  # silent: Rip Van Winkle, Oct 13-14


def test_a_step_out_of_time_waits_behind_the_others_and_a_stuck_one_blocks_its_next(tmp_path, monkeypatch):
    monkeypatch.setattr(q, 'DB', str(tmp_path / 'q.sqlite'))
    monkeypatch.setattr(q, 'ALERTS', str(tmp_path / 'alerts.json'))
    a = q.add('F1', 'a-file', ['true'])
    b = q.add('F2', 'b-file', ['true'])
    c = q.add('F1', 'a-report', ['true'], after=a)
    con = q.connect()
    assert q.next_step(con)[0] == a
    con.execute('update queue set deferred = ? where id = ?', (q.now(), a))
    con.commit()
    assert q.next_step(con)[0] == b  # a ran out of time: b takes its turn
    con.execute("update queue set status = 'stuck' where id = ?", (a,))
    con.execute("update queue set status = 'done' where id = ?", (b,))
    con.commit()
    q.set_alert(a, 'a-file', 'stuck', 'no progress')
    assert q.next_step(con) is None and con.execute('select status from queue where id = ?', (c,)).fetchone()[0] == 'blocked'
    assert [x['id'] for x in q.alerts()] == [a]
    q.retry(a, minutes=300)
    assert q.alerts() == [] and q.next_step(con)[0] == a
    assert con.execute('select status from queue where id = ?', (c,)).fetchone()[0] == 'waiting'
    assert con.execute('select minutes from queue where id = ?', (a,)).fetchone()[0] == 300


def test_the_deck_shows_an_experiment_the_queue_gave_up_on(tmp_path, monkeypatch):
    import json
    from app import deck, lights
    monkeypatch.setattr(lights, 'card', lambda: (12.0, 0))
    monkeypatch.setattr(lights, 'who', lambda: 'idle')
    monkeypatch.setattr(deck, 'EXPERIMENT_ALERTS', str(tmp_path / 'alerts.json'))
    assert deck.gpu()[0] == 'idle'
    (tmp_path / 'alerts.json').write_text(json.dumps([{'id': 1, 'holder': 'isis-file', 'status': 'stuck'}]))
    who, load, label = deck.gpu()
    assert who == 'alert' and label.startswith('⚠') and 'Isis' in label
