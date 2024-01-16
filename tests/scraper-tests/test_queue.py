from scrapers.queue import Queue

def test_instantiation():
    queue = Queue()
    assert queue is not None
    assert isinstance(queue, Queue)