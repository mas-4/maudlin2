"""Widely seen Bluesky posts shown with a narrative: only from Bluesky's own counts, never from people who asked not to
be shown to logged-out visitors, and gone when deleted."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.models import Base
from app import bluesky_examples as bx

A, B, C, D = (f'at://did:plc:{x}/app.bsky.feed.post/r{x}' for x in 'abcd')


@pytest.fixture(autouse=True)
def db(monkeypatch):
    """An in-memory data.db: the data folder is production's"""
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


def post(uri, likes=0, reposts=0, labels=(), author_labels=()):
    did = uri.split('/')[2]
    return {'uri': uri, 'cid': 'cid-' + did, 'likeCount': likes, 'repostCount': reposts, 'replyCount': 0, 'quoteCount': 0,
            'labels': [{'val': v} for v in labels], 'author': {'did': did, 'handle': did + '.bsky.social',
                                                                 'labels': [{'val': v} for v in author_labels]}}


def test_shown_only_when_widely_seen_and_allowed(monkeypatch):
    answers = {A: post(A, likes=30, reposts=4), B: post(B, likes=40, author_labels=['!no-unauthenticated']),
               C: post(C, likes=5)}  # D: deleted
    calls = []

    def get(method, key, values):
        calls.append(method)
        if method == 'app.bsky.feed.getPosts':
            return {'posts': [answers[u] for u in values if u in answers]}
        return {'profiles': [{'did': 'did:plc:c', 'followersCount': 12000, 'labels': []}]}
    cache = bx.refresh([A, B, C, D], get=get, sleep=lambda s: None)
    assert calls == ['app.bsky.feed.getPosts', 'app.bsky.actor.getProfiles']  # followers only for the borderline post
    assert cache[D]['gone'] and cache[B]['hidden'] and cache[C]['followers'] == 12000
    shown = bx.examples([D, B, C, A], cache)
    assert [p['uri'] for p in shown] == [A, C]  # most interaction first; a big account's post with a few counts
    assert shown[0]['url'] == 'https://bsky.app/profile/did:plc:a/post/ra' and shown[0]['cid'] == 'cid-did:plc:a'
    # Looked up again later: deleted since, so it drops off
    del answers[A]
    monkeypatch.setattr(bx, 'now', lambda: bx.dt.fromisoformat(cache[A]['checked']) + bx.RECHECK)
    cache = bx.refresh([A], get=get, sleep=lambda s: None)
    assert bx.examples([A], cache) == []


def test_a_down_api_keeps_what_we_had():

    def down(*a):
        raise OSError('down')
    assert bx.refresh([A], get=down, sleep=lambda s: None) == {}


def test_kept_in_the_table_and_read_back_whole(monkeypatch):
    def get(method, key, values):
        return {'posts': [post(A, likes=30)]} if method == 'app.bsky.feed.getPosts' else {'profiles': []}
    cache = bx.refresh([A, B], get=get, sleep=lambda s: None)
    assert bx.load() == cache and cache[B]['gone'] and 'likes' not in cache[B]
    # Past KEEP from its first lookup a post is dropped
    monkeypatch.setattr(bx, 'now', lambda: bx.dt.fromisoformat(cache[A]['first']) + bx.KEEP + bx.td(hours=1))
    assert bx.refresh([], get=get, sleep=lambda s: None) == {} and bx.load() == {}
