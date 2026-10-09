import threading
import time

from app.analysis import llm


def test_parallel_keeps_order_and_runs_at_once():
    inside, most = [0], [0]
    lock = threading.Lock()

    def fn(x):
        with lock:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with lock:
            inside[0] -= 1
        return x * 2
    assert llm.parallel(fn, [3, 1, 2, 5, 4, 6]) == [6, 2, 4, 10, 8, 12]
    assert most[0] == llm.PARALLEL


def test_parallel_skips_what_isnt_begun_by_the_budget():
    def fn(x):
        time.sleep(0.2)
        return x
    got = llm.parallel(fn, list(range(12)), budget=0.1, workers=2)
    assert got[:2] == [0, 1] and got[-1] is None


def test_parallel_with_nothing():
    assert llm.parallel(lambda x: x, []) == []
