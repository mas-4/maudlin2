from scraper.main import Queue


def test_instantiation():
    queue = Queue()
    assert queue is not None
    assert isinstance(queue, Queue)


def test_queue():
    queue = Queue()
    assert len(queue.scrapers) > 0, "Queue should have items"
    queue.run()
    assert len(queue.scrapers) == 0, "Queue should have no items after running"
