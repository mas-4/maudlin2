from datetime import datetime

from app import chyrons

DAY = ("date_time_(UTC)\tchannel\tduration\thttps://archive.org/details/\ttext\n"
       "2026-10-05 00:01:00\tMSNOW\t45\tMSNOW_20261005_000000_Nicolle_Wallace_Presents_92NY_on_MS_NOW/start/60\tNICOI I E WAL ACE\n"
       "2026-10-05 00:02:00\tFOXNEWSW\t11\tFOXNEWSW_20261005_000000_Life_Liberty__Levin/start/120\tSAMUEL ALITO\\nJUSTICE\n"
       "2026-10-05 00:03:00\tKTVU\t9\tKTVU_20261005_000000_News/start/1\tlocal station, not ours\n")


def test_a_day_of_chyrons_reads_with_program_names(monkeypatch, tmp_path):
    monkeypatch.setattr(chyrons, 'FOLDER', str(tmp_path))
    (tmp_path / '2026-10-05.tsv').write_text(DAY)
    first, second = chyrons.rows('2026-10-05')
    assert first['channel'] == 'MSNOW' and first['seconds'] == 45 and first['at'] == datetime(2026, 10, 5, 0, 1)
    assert first['program'] == 'Nicolle Wallace Presents 92NY on MS NOW'
    assert second['text'] == 'SAMUEL ALITO\nJUSTICE' and second['link'].startswith('https://archive.org/details/FOXNEWSW')
    assert chyrons.rows('2026-10-06') == []


def test_each_run_reads_today_and_finishes_yesterday_once(monkeypatch, tmp_path):
    monkeypatch.setattr(chyrons, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(chyrons, 'STATE', str(tmp_path / 'state.json'))
    asked = []
    monkeypatch.setattr(chyrons, 'fetch_day', lambda day: asked.append(day) or 10)
    chyrons.fetch_chyrons(datetime(2026, 10, 6, 9))
    chyrons.fetch_chyrons(datetime(2026, 10, 6, 10))
    assert asked == ['2026-10-05', '2026-10-06', '2026-10-06']
