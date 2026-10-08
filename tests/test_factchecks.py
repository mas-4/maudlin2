import numpy as np

from app.analysis import clustering, factchecks, llm


def test_fact_checks_tie_only_above_the_floor_by_forced_choice(monkeypatch, tmp_path):
    monkeypatch.setattr(factchecks, 'STORY_CACHE', str(tmp_path / 'fc.json'))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    sim = np.array([[1, 0, .7, .2], [0, 1, .55, .5], [.7, .55, 1, 0], [.2, .5, 0, 1]])
    monkeypatch.setattr(clustering, 'story_similarity', lambda texts: (sim, 0.8, 'mxbai-embed-large'))
    prompts = []
    monkeypatch.setattr(llm, 'complete_json', lambda prompt, schema, max_tokens=0: prompts.append(prompt) or
                        {'reason': '', 'pick': '1'})
    items = [{'title': 'FAKE video of FlyDubai pilot', 'summary': '', 'source': 'Lead Stories'},
             {'title': 'Taxpayer-funded ads', 'summary': '', 'source': 'FactCheck.org'}]
    found = factchecks.for_stories({1: 'FlyDubai co-pilot attack', 2: 'Paxton ads air'}, items)
    assert found == {1: [items[0]]}
    assert len(prompts) == 1 and 'is a fact-checker' in prompts[0]  # the second was under the floor: never asked


def test_a_fact_check_is_read_from_its_piece_and_a_filed_claim_keeps_its_wording(monkeypatch, tmp_path):
    import json

    from app.analysis import factcheck_text as ft, motif_index as mi
    monkeypatch.setattr(factchecks, 'LABELS', str(tmp_path / 'labels.json'))
    monkeypatch.setattr(ft, 'TEXTS', str(tmp_path / 'texts.json'))
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 2, 'entries': {}, 'claims': {mi.key('Old claim, filed'): ['M1']},
             'corrections': {'Pols are bad': 'Critics say a senator lied about a vote'}})
    (tmp_path / 'labels.json').write_text(json.dumps({'https://a.example/1': {'claim': 'Old claim, filed'}}))
    (tmp_path / 'texts.json').write_text(json.dumps({'https://a.example/1': {'text': 'THE PIECE SAYS posts claimed X.'},
                                                      'https://a.example/2': {'text': 'Another piece.'}}))
    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(llm, 'model', lambda: 'm')
    prompts = []

    def answer(prompt, schema, max_tokens=0):
        prompts.append(prompt)
        return {'claim': 'Posts on X claim the governor banned prayer', 'context': 'Viral posts; nothing of the kind.',
                'genre': schema['properties']['genre']['enum'][0], 'motif_chapter': schema['properties']['motif_chapter']['enum'][0],
                'motif': '', 'politics': True, **{k: '' for k in schema['required'] if k not in ('claim', 'context', 'genre',
                                                                                              'motif_chapter', 'motif', 'politics')}}
    monkeypatch.setattr(llm, 'complete_json', answer)
    now = '2026-10-08T12:00:00+00:00'
    items = [{'url': f'https://a.example/{n}', 'title': 'Did the governor ban prayer?', 'summary': '', 'source': 'Snopes',
              'published': now} for n in (1, 2)]
    labels = factchecks.label_all(items)
    assert 'THE PIECE SAYS' in prompts[0] and '"Pols are bad" became "Critics say a senator lied about a vote"' in prompts[0]
    assert labels['https://a.example/1']['claim'] == 'Old claim, filed'  # filed: the person's claim stays as it is
    assert labels['https://a.example/1']['claim from the piece'].startswith('Posts on X')
    assert labels['https://a.example/2']['claim'].startswith('Posts on X') and labels['https://a.example/2']['read'] == 'piece'


def test_a_piece_s_text_is_its_article_not_the_page_around_it():
    from app.analysis import factcheck_text as ft
    html = ('<html><body><nav><p>Menu Home About</p></nav><article><h2>Claim</h2><p>Posts say the dam broke.</p>'
            '<script>x()</script><p>It did not.</p></article><footer><p>Copyright</p></footer></body></html>')
    assert ft._clean(html) == 'Claim\nPosts say the dam broke.\nIt did not.'


def test_robots_txt_is_read_under_our_own_name(monkeypatch):
    from app.analysis import factcheck_text as ft

    class R:
        def __init__(self, code, text=''):
            self.status_code, self.text, self.ok = code, text, code < 400
    seen = {}

    def get(url, timeout=0, headers=None):
        seen[url] = headers['User-Agent']
        return {'https://a.example/robots.txt': R(200, 'User-agent: GPTBot\nDisallow: /\nUser-agent: *\nDisallow: /private/'),
                'https://b.example/robots.txt': R(403), 'https://c.example/robots.txt': R(404)}[url]
    monkeypatch.setattr(ft.requests, 'get', get)
    p = ft.Polite()
    assert p.allowed('https://a.example/fact-check/x') and not p.allowed('https://a.example/private/y')
    assert not p.allowed('https://b.example/x') and p.allowed('https://c.example/x')
    assert set(seen.values()) == {ft.USER_AGENT}
