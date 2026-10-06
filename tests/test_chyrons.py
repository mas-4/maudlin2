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


def test_cleaning_asks_once_per_caption_and_skips_the_clock(monkeypatch, tmp_path):
    monkeypatch.setattr(chyrons, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(chyrons, 'CLEAN', str(tmp_path / 'clean.json'))
    day = ("date_time_(UTC)\tchannel\tduration\thttps://archive.org/details/\ttext\n"
           "2026-10-05 10:00:00\tCNNW\t40\tCNNW_20261005_100000_CNN_News_Central/start/1\tTRUMP RALLIES IN RED STATES. . Max Foster | CNN Anchor\n"
           "2026-10-05 10:01:00\tCNNW\t35\tCNNW_20261005_100000_CNN_News_Central/start/61\tTRUMP RALIIES IN RED STATES\n"
           "2026-10-05 10:02:00\tMSNOW\t30\tMSNOW_20261005_100000_Morning_Joe/start/1\t1 IVE > 9:47am\n")
    (tmp_path / '2026-10-05.tsv').write_text(day)
    from app.analysis import llm
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    asked = []

    def complete(prompt, schema, max_tokens, model):
        lines = [l.split('. ', 1)[1] for l in prompt.splitlines() if l[:1].isdigit() and '. ' in l]
        asked.append(lines)
        return {'lines': [{'n': n, 'kind': 'name' if '|' in l else 'headline', 'text': l.upper().replace('RALIIES', 'RALLIES')}
                          for n, l in enumerate(lines, 1)]}
    monkeypatch.setattr(llm, 'complete_json', complete)
    assert chyrons.clean_day('2026-10-05', ['Trump rallies']) == 4
    assert len(asked) == 1 and sorted(asked[0]) == ['Max Foster | CNN Anchor', 'TRUMP RALLIES IN RED STATES']  # one per group
    store = chyrons.read_json(chyrons.CLEAN, {})
    assert store['CNNW|TRUMP RALIIES IN RED STATES'] == {'kind': 'headline', 'text': 'TRUMP RALLIES IN RED STATES'}
    assert store['MSNOW|1 IVE > 9:47am']['kind'] == 'junk'  # the clock, without asking
    assert chyrons.clean_day('2026-10-05', []) == 0  # nothing left


def test_headline_captions_match_the_story_theyre_about(monkeypatch, tmp_path):
    import numpy as np
    monkeypatch.setattr(chyrons, 'FOLDER', str(tmp_path))
    monkeypatch.setattr(chyrons, 'CLEAN', str(tmp_path / 'clean.json'))
    (tmp_path / '2026-10-05.tsv').write_text(
        "date_time_(UTC)\tchannel\tduration\thttps://archive.org/details/\ttext\n"
        "2026-10-05 18:05:00\tCNNW\t40\tCNNW_x/start/1\tC0-PILOT MEANT TO CRASH\n"
        "2026-10-05 18:06:00\tCNNW\t30\tCNNW_x/start/61\tWEATHER AHEAD\n")
    chyrons.write_json(chyrons.CLEAN, {'CNNW|C0-PILOT MEANT TO CRASH': {'kind': 'headline', 'text': 'CO-PILOT MEANT TO CRASH'},
                                       'CNNW|WEATHER AHEAD': {'kind': 'headline', 'text': 'WEATHER AHEAD'}})
    monkeypatch.setattr(chyrons, 'front_at', lambda when: [{'id': 70, 'label': 'Dubai flight attack', 'outlets': 30, 'rank': 2,
                                                            'headlines': ['Co-pilot attacked captain']}])
    vec = {'CO-PILOT MEANT TO CRASH': [1, 0], 'WEATHER AHEAD': [0, 1], 'Dubai flight attack': [0.8, 0.6],
           'Co-pilot attacked captain': [0.95, 0.31]}
    from app.analysis import clustering
    monkeypatch.setattr(clustering, 'ollama_embed', lambda texts: np.array([vec[t] for t in texts], float))
    first, second = chyrons.match_day('2026-10-05')
    assert first['story'] == 70 and first['rank'] == 2 and first['seconds'] == 40
    assert 'story' not in second  # nothing close enough
    assert chyrons.read_json(str(tmp_path / 'matched-2026-10-05.json'), [])[0]['text'] == 'CO-PILOT MEANT TO CRASH'


def test_bbcs_logo_comes_off_its_headlines():
    assert list(chyrons.caption_lines('Quebec separatist party projected to win election. B EE NEWS')) == \
        ['Quebec separatist party projected to win election']
    assert list(chyrons.caption_lines('B EAE NEWS')) == []
    assert list(chyrons.caption_lines('TRUMP SAYS BIG NEWS')) == ['TRUMP SAYS BIG NEWS']
    assert list(chyrons.caption_lines('HEADLINE HERE. . Max Foster | CNN Anchor')) == ['HEADLINE HERE', 'Max Foster | CNN Anchor']
