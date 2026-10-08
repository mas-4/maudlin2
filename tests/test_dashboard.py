"""app/dashboard.py: the hourly runs read from systemd's log (a stopped one shown as failed), the card's minute log
summed every ten minutes, and one part failing leaves the rest showing."""
from app import dashboard


def test_runs_are_read_from_the_log_and_a_run_stopped_at_its_limit_shows_as_failed(monkeypatch):
    log = ['2026-10-08T15:00:04-04:00 host systemd[1]: Starting Maudlin scrape and site build...',
           '2026-10-08T15:45:05-04:00 host systemd[1]: maudlin-scrape.service: Failed with result \'timeout\'.',
           '2026-10-08T16:00:04-04:00 host systemd[1]: Starting Maudlin scrape and site build...',
           '2026-10-08T16:36:29-04:00 host systemd[1]: Finished Maudlin scrape and site build.']
    monkeypatch.setattr(dashboard, '_journal', lambda unit, hours: log)
    assert dashboard.runs() == [{'start': '2026-10-08T15:00:04', 'minutes': 45.0, 'ok': False},
                                {'start': '2026-10-08T16:00:04', 'minutes': 36.4, 'ok': True}]


def test_the_cards_minute_log_is_summed_every_ten_minutes(monkeypatch, tmp_path):
    from datetime import datetime as dt
    now = dt.now().strftime('%Y/%m/%d %H:%M')
    (tmp_path / 'gpu_log.csv').write_text(f'{now}:05.123, 70, 90 %, 280.0 W, 40 %, 8000 MiB\n'
                                          f'{now}:35.000, 74, 50 %, 200.0 W, 44 %, 8000 MiB\nnot a line\n')
    monkeypatch.setattr(dashboard.Config, 'data', str(tmp_path))
    assert [{k: p[k] for k in ('temp', 'load', 'watts')} for p in dashboard.gpu()] == [{'temp': 74, 'load': 70, 'watts': 240}]


def test_a_part_that_fails_shows_its_error_and_the_rest_still_show(monkeypatch):
    def broken():
        raise RuntimeError('no log')
    monkeypatch.setattr(dashboard, 'PARTS', {'runs': broken, 'machine': lambda: {'disk free GB': 1}})
    monkeypatch.setattr(dashboard, '_parts', {})
    d = dashboard.gather(fresh=True)
    assert d['runs'] == {'error': 'RuntimeError: no log'} and d['machine'] == {'disk free GB': 1} and 'at' in d
