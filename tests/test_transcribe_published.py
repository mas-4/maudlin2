"""app/transcribe.py: a transcript a show publishes (WebVTT or SRT) becomes segments like Whisper's, its cues joined
into a speaker's sentences; pending items that have one are taken from the show, not Whisper."""
from app import transcribe

VTT = '''WEBVTT - an episode

0:00:00.200 --> 0:00:02.800
<v Speaker 1>So one of the biggest races this cycle is,

0:00:02.860 --> 0:00:05.830
<v Speaker 1>of course, the Senate seat in Michigan.

0:00:06.000 --> 0:00:07.500
<v Speaker 2>Right.
'''
SRT = '''1
00:00:01,000 --> 00:00:03,500
Hello there

2
00:00:03,600 --> 00:00:05,000
and welcome.
'''


def test_cues_become_a_speakers_sentences():
    assert transcribe.parse_timed(VTT) == [
        {'start': 0.2, 'end': 5.8, 'text': 'So one of the biggest races this cycle is, of course, the Senate seat in Michigan.',
         'speaker': 'Speaker 1'},
        {'start': 6.0, 'end': 7.5, 'text': 'Right.', 'speaker': 'Speaker 2'}]
    assert transcribe.parse_timed(SRT) == [{'start': 1.0, 'end': 5.0, 'text': 'Hello there and welcome.'}]


def test_an_item_with_a_published_transcript_skips_whisper(monkeypatch, tmp_path):
    import json

    from app import sidefeeds

    class Item:
        def __init__(self, i, url):
            self.id, self.url, self.title = i, url, f'item {i}'
    links = tmp_path / 'links.json'
    links.write_text(json.dumps({'https://s.example/1': 'https://t.example/1.vtt'}))
    monkeypatch.setattr(sidefeeds, 'TRANSCRIPTS', str(links))

    class R:
        text = VTT

        def raise_for_status(self):
            pass
    monkeypatch.setattr(transcribe.rq, 'get', lambda url, **k: R())
    monkeypatch.setattr(transcribe, 'PAUSE', 0)
    saved = []
    monkeypatch.setattr(transcribe, 'save', lambda i, segs, secs, model='': saved.append((i, len(segs), secs, model)))
    assert transcribe.published_transcripts([Item(1, 'https://s.example/1'), Item(2, 'https://s.example/2')]) == 1
    assert saved == [(1, 2, 7.5, 'published by the show')]
