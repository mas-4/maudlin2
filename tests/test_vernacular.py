import pytest
"""The Bluesky and Mastodon sample: what's kept, what's scrubbed, what's skipped."""
from app import vernacular as v


def test_scrub_hides_handles_and_links():
    assert v.scrub('@ken.bsky.social said https://www.nytimes.com/2026/a.html cc @bob') == \
        '@someone said [link: nytimes.com] cc @someone'


def message(text, op='create', langs=('en',), labels=None, embed=None, reply=False):
    record = {'text': text, 'langs': list(langs), 'createdAt': '2026-10-04T12:00:00Z'}
    if labels:
        record['labels'] = {'values': [{'val': labels}]}
    if embed:
        record['embed'] = {'$type': embed}
    if reply:
        record['reply'] = {}
    return {'did': 'did:plc:abc', 'kind': 'commit',
            'commit': {'operation': op, 'collection': 'app.bsky.feed.post', 'rkey': '1', 'record': record}}


def test_rows_keep_english_unlabeled_text_and_fingerprint_authors():
    kind, values = v.row(message('They are putting something in the water again, my aunt says'), 'pepper')
    assert kind == 'create' and values[4].startswith('They are putting')
    assert values[1] == v.fingerprint('did:plc:abc', 'pepper') and 'did:plc' not in values[1]
    assert values[9] == 'at://did:plc:abc/app.bsky.feed.post/1'  # its address, to embed it if it was widely seen
    assert v.row(message('Elles mettent quelque chose dans l eau', langs=('fr',)), 'p') is None
    assert v.row(message('A long enough post with an adult label', labels='porn'), 'p') is None
    assert v.row(message('lol'), 'p') is None
    assert v.row(message('', op='delete'), 'pepper') == ('delete', v.fingerprint('did:plc:abc/1', 'pepper'))
    _, media = v.row(message('A long enough post with a picture attached', embed='app.bsky.embed.images'), 'p')
    assert media[7] == 1


def test_mastodon_keeps_only_opted_in_people():
    status = {'uri': 'u', 'content': '<p>They are putting something in the water, my aunt says</p>',
              'language': 'en', 'account': {'uri': 'a', 'indexable': True, 'bot': False}, 'sensitive': False,
              'spoiler_text': '', 'reblog': None, 'in_reply_to_id': None, 'quote': None, 'media_attachments': []}
    assert v.mastodon_row(status, 'p')[4] == 'They are putting something in the water, my aunt says'
    assert v.mastodon_row({**status, 'account': {'uri': 'a', 'indexable': False}}, 'p') is None
    assert v.mastodon_row({**status, 'account': {'uri': 'a', 'indexable': True, 'bot': True}}, 'p') is None
    assert v.mastodon_row({**status, 'spoiler_text': 'politics'}, 'p') is None


@pytest.mark.parametrize('text, scrubbed', [
    ('Click for the full video! youtu.be/eff3Rw7KhIc', 'Click for the full video! [link: youtu.be]'),
    ('www.twitch.tv/somebody', '[link: twitch.tv]'),  # a shortened link without https:// can name an account
    ('rated 3.5/10, e.g. bad', 'rated 3.5/10, e.g. bad'),
])
def test_scrub_cuts_shortened_links_to_their_site(text, scrubbed):
    assert v.scrub(text) == scrubbed
