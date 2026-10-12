"""app/lights.py: what the card shows for each state (no hardware)"""
from app import lights


def state(**kw):
    return {'who': 'idle', 'load': 0.0, 'temp': 50.0, 'failed': False, **kw}


def test_the_day_shows_who_has_the_gpu():
    assert lights.look(state(who='worker', load=90), False) == ('Breathing', lights.TEAL, 0, 5)
    assert lights.look(state(who='worker', load=20), False)[3] == 2  # dimmer at light load
    assert lights.look(state(who='experiment', load=60), False)[:2] == ('Flowing', lights.VIOLET)
    assert lights.look(state(who='hourly', load=60), False)[:2] == ('Flowing', lights.AMBER)
    assert lights.look(state(), False) == ('Breathing', lights.IDLE, 0, 2)


def test_the_night_stays_dark():
    assert lights.look(state(), True) == ('Direct', lights.DARK, 0, 0)
    assert lights.look(state(who='worker', load=90), True) == ('Direct', lights.DARK, 0, 0)  # working: still dark
    assert lights.look(state(who='worker', load=90, failed=True, temp=95), True)[1] == lights.DARK  # no alarms at night


def test_a_failed_run_and_heat_show():
    assert lights.look(state(failed=True), False)[:2] == ('Doubleflashing', lights.RED)
    assert lights.look(state(who='hourly', failed=True, load=50), False)[1] == lights.AMBER  # the next run is trying
    assert lights.look(state(who='worker', load=90, temp=95), False)[:2] == ('Flashing', lights.RED)
    warm = lights.look(state(who='worker', load=90, temp=89), False)[1]
    assert warm != lights.TEAL and warm[0] > lights.TEAL[0]  # toward orange


def test_the_unicorn_key_brings_the_rainbow_for_a_while(monkeypatch, tmp_path):
    import json
    import time
    assert lights.look(state(party=True), False)[0] == 'Rainbow'
    assert lights.look(state(party=True), True)[0] == 'Rainbow'  # the person pressed it: night too
    assert lights.look(state(party=True, who='worker', temp=95), False)[:2] == ('Flashing', lights.RED)  # heat first
    from app.utils import Config
    monkeypatch.setattr(Config, 'data', str(tmp_path))
    assert not lights.party()
    (tmp_path / lights.PARTY).write_text(json.dumps({'until': time.time() + 30}))
    assert lights.party()
    (tmp_path / lights.PARTY).write_text(json.dumps({'until': time.time() - 1}))
    assert not lights.party()


def test_the_night_runs_from_sunset_to_sunrise(tmp_path, monkeypatch):
    from datetime import date, datetime, timedelta, timezone
    from app.utils import Config
    rise, set_ = lights.sun(date(2026, 10, 12), 28.15, -82.76)  # a Florida town: about 07:35 and 19:05 EDT
    assert abs(rise - 11.6) < 0.2 and abs(set_ - 23.1) < 0.2
    monkeypatch.setattr(Config, 'data', str(tmp_path))
    edt = timezone(timedelta(hours=-4))
    at = lambda h, m=0: datetime(2026, 10, 12, h, m, tzinfo=edt)  # noqa: E731
    assert lights.night(at(23, 30)) and not lights.night(at(12))  # no place yet: the old hours
    assert lights.night(at(7, 30)) and not lights.night(at(20))
    (tmp_path / lights.PLACE).write_text('{"lat": 28.15, "lon": -82.76}')
    assert lights.night(at(7, 15)) and not lights.night(at(8))  # dark until the sun's up
    assert not lights.night(at(18, 45)) and lights.night(at(19, 30)) and lights.night(at(2))
