"""app/lights.py: what the card shows for each state (no hardware)"""
from app import lights


def state(**kw):
    return {'who': 'idle', 'load': 0.0, 'temp': 50.0, 'failed': False, **kw}


def test_the_day_shows_who_has_the_gpu():
    assert lights.look(state(who='worker', load=90), 12) == ('Breathing', lights.TEAL, 0, 5)
    assert lights.look(state(who='worker', load=20), 12)[3] == 2  # dimmer at light load
    assert lights.look(state(who='experiment', load=60), 12)[:2] == ('Flowing', lights.VIOLET)
    assert lights.look(state(who='hourly', load=60), 12)[:2] == ('Flowing', lights.AMBER)
    assert lights.look(state(), 12) == ('Breathing', lights.IDLE, 0, 2)


def test_the_night_stays_dark():
    assert lights.look(state(), 2) == ('Direct', lights.DARK, 0, 0)
    assert lights.look(state(who='worker', load=90), 23.5) == ('Breathing', lights.EMBER, 0, 1)
    assert lights.look(state(who='worker', load=90, failed=True, temp=95), 3)[1] == lights.EMBER  # no alarms at night


def test_a_failed_run_and_heat_show():
    assert lights.look(state(failed=True), 12)[:2] == ('Doubleflashing', lights.RED)
    assert lights.look(state(who='hourly', failed=True, load=50), 12)[1] == lights.AMBER  # the next run is trying
    assert lights.look(state(who='worker', load=90, temp=95), 12)[:2] == ('Flashing', lights.RED)
    warm = lights.look(state(who='worker', load=90, temp=89), 12)[1]
    assert warm != lights.TEAL and warm[0] > lights.TEAL[0]  # toward orange


def test_the_unicorn_key_brings_the_rainbow_for_a_while(monkeypatch, tmp_path):
    import json
    import time
    assert lights.look(state(party=True), 12)[0] == 'Rainbow'
    assert lights.look(state(party=True), 2)[0] == 'Rainbow'  # the person pressed it: night too
    assert lights.look(state(party=True, who='worker', temp=95), 12)[:2] == ('Flashing', lights.RED)  # heat first
    from app.utils import Config
    monkeypatch.setattr(Config, 'data', str(tmp_path))
    assert not lights.party()
    (tmp_path / lights.PARTY).write_text(json.dumps({'until': time.time() + 30}))
    assert lights.party()
    (tmp_path / lights.PARTY).write_text(json.dumps({'until': time.time() - 1}))
    assert not lights.party()
