"""app/gaming.py: gaming mode holds the worker, experiments and hourly runs back until it's off, or its time is up"""
import time

from app import gaming, gpu_lease, worker


def test_gaming_mode_holds_the_work_back_until_off(monkeypatch, tmp_path):
    monkeypatch.setattr(gaming, 'FLAG', str(tmp_path / 'gaming.json'))
    monkeypatch.setattr(gaming, 'free_card', lambda after_run=False: [])  # never the real Ollama's models
    monkeypatch.setattr(worker, 'run_going', lambda: False)
    monkeypatch.setattr(gpu_lease, 'held', lambda: None)
    assert gaming.active() is None and worker.yielding() is None and not gpu_lease._hourly_run_going()
    assert gaming.main(['status']) == 1
    gaming.main(['on'])
    assert gaming.active() and worker.yielding() == 'gaming mode' and gpu_lease._hourly_run_going()
    assert gaming.main(['status']) == 0  # how scripts/run.sh knows to skip the hourly run
    gaming.main(['toggle'])
    assert gaming.active() is None and worker.yielding() is None


def test_gaming_mode_turns_itself_off_at_most_after_max_hours(monkeypatch, tmp_path):
    monkeypatch.setattr(gaming, 'FLAG', str(tmp_path / 'gaming.json'))
    monkeypatch.setattr(gaming, 'free_card', lambda after_run=False: [])
    on = gaming.turn_on(hours=100)
    assert on['until'] - on['since'] == gaming.MAX_HOURS * 3600
    monkeypatch.setattr(time, 'time', lambda: on['until'] + 1)
    assert gaming.active() is None  # past its time: off, though the flag is still there


def test_in_gaming_mode_the_hourly_run_scrapes_but_judges_nothing(monkeypatch):
    """main.py --gaming: headlines kept unjudged, never a call to the model (judged by the first run after)"""
    from app.analysis import llm, newsfilter
    asked = []
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(newsfilter, 'judge', lambda title, agency: asked.append(title))
    monkeypatch.setattr(newsfilter, 'DEFER', True)
    got = newsfilter.assess(['Senate passes the budget', 'Ten best pies'], 'AP')
    assert asked == [] and all(r['news_score'] is None and r['scored_by'] is None for r in got)
