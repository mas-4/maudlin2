"""Folklore and rumors (work in progress, #142, #153): one catalog of what's told, from three sources (Oct 8; until
then Folklore and Rumors were two pages). A card per claim:
- retold online: the folklore-shaped narratives in what people say on Bluesky and Mastodon, from the latest nightly
  report (app/narratives.py), with how many people tell it, how varied their wording is, and the news it rides on;
- told on the shows: claims told on two or more of the podcasts, call-in and video shows we transcribe
  (app/analysis/show_claims.py), with which shows;
- fact-checked: the rumors fact-checkers examined in the last few weeks (app/analysis/factchecks.py); the verdict
  is always the fact-checker's own, behind its link. A check already linked from a narrative's card isn't repeated.
Each card carries the motifs it's filed under in our motif index, and the person's genres of those motifs.

People's own posts are never shown on the published site, only the model's summary of what they share: even without
handles, a quoted post can be searched back to its author. Local preview builds (debug) show a few versions, so the
research can be checked."""
import glob
import json
import os
from collections import Counter
from datetime import date

from app.analysis.rumor_shapes import CONSPIRACY_SCOPES, EMOJI as SHAPE_EMOJI, RUMOR_CLASSES
from app import bluesky_examples
from app.analysis import accusations, circulation, factchecks, motif_index, narrative_threads, show_claims
from app.site.common import TemplateHandler
from app.utils import Config, get_logger
from app.utils.store import read_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
# Fewer tellers than this aren't shown: at five to nine people (half of what the finder keeps) most groups are a
# handful reacting to the same news, not a story people retell. The floor grows with the sample, 1 in PEOPLE_SHARE.
MIN_PEOPLE = 10
PEOPLE_SHARE = 2500
NOT_STORIES = {'news report or shared reaction', 'none: a shared topic, not a retold narrative'}  # no cast or motif
SIDE_INK = {'left': '#1a5cff', 'right': '#e0102e', 'both': '#7a3fd1', 'none': '#8a8f98'}


WITHHELD = os.path.join(FOLDER, 'withheld.json')  # narratives pulled by hand: [{claim, reason, at}]


def withheld() -> set[str]:
    """Claims withheld from the page by hand after a misreading (Oct 4: a group of trans people talking about their
    own identity was labeled as spreading an anti-trans claim one of them had quoted)."""
    return {w['claim'] for w in read_json(WITHHELD, [])}


FOCUS_EPISODES = 4  # Focus Group episodes shown, the latest
MOTIF_CHIPS = 12  # motif filters at most
CHECK_DAYS = 30  # fact-checks this recent
# Where a card's claim was heard: the source chips on each card and the filter row
SOURCES = {'posts': {'emoji': '🧶', 'name': 'retold online', 'about': 'Told by many people in their own words on Bluesky and Mastodon'},
           'shows': {'emoji': '🎙️', 'name': 'on the shows', 'about': 'Told on two or more of the podcasts, call-in and video shows we transcribe'},
           'checks': {'emoji': '🔎', 'name': 'fact-checked', 'about': 'Examined by a fact-checker in the last 30 days'}}
MOVED = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Moved</title>'
         '<link rel="canonical" href="{to}"><meta http-equiv="refresh" content="0; url={to}"></head>'
         '<body><p>Rumors are now part of <a href="{to}">Folklore and rumors</a>.</p></body></html>')
SHOW_INK = {'left': '#3a86ff', 'right': '#ff4f6d', 'center': '#b8b8c8'}  # as the front page's shows (page_headlines)


def motif_counts(cards: list[dict]) -> list[tuple[dict, int]]:
    """(motif, how many cards carry it) for the motif filter row: motifs on two or more cards, most first (one on a
    single card would filter down to that card)."""
    seen, counts = {}, Counter()
    for c in cards:
        for m in c['motifs']:
            seen[m['id']] = m
            counts[m['id']] += 1
    return [(seen[i], n) for i, n in counts.most_common() if n >= 2][:MOTIF_CHIPS]


def motif_cards(index: dict, claim: str) -> list[dict]:
    """The motif-index entries a claim is filed under, for its card: id, name and how many claims each holds. Only
    motifs a person has verified, and only if they saw this claim in it (motif_index.public)."""
    k = motif_index.key(claim) if claim else None
    return [{'id': e['id'], 'name': e['name'], 'count': len(motif_index.public_claims(e)), 'note': motif_index.public_note(e),
             'genre': motif_index.genre_of(e)}
            for e in (motif_index.entries_of(index, claim) if claim else [])
            if motif_index.public(e) and k in set(e.get('done') or [])]


def genres(motifs: list[dict]) -> list[str]:
    """A card's genres: those the person gave the motifs it's filed under (a genre belongs to a motif, not a claim)"""
    return sorted({m['genre'] for m in motifs if m.get('genre')}, key=str.lower)


def counted(cards: list[dict], key: str) -> list[tuple[str, int]]:
    """(value, cards with it) for a filter row, most first; `key` a card's single value or its list of values"""
    return Counter(v for c in cards for v in (c[key] if isinstance(c.get(key), list) else [c.get(key)]) if v).most_common()


def checked_cards(index: dict, linked: set[str]) -> list[dict]:
    """A card per fact-check from the last CHECK_DAYS that names a claim, newest first, except those already linked
    from a narrative's card (`linked`, their urls): the claim in the model's words, its shape, and whether people in
    our social sample are telling it (app/analysis/circulation.py)"""
    try:
        items = factchecks._items(CHECK_DAYS)
        labels = factchecks.label_all(items)
    except Exception as e:  # noqa: BLE001 - e.g. no side_item table on a database that hasn't migrated
        logger.warning("Folklore: no fact-checks (%s)", e)
        return []
    looked = circulation.load()
    seen = looked.get('claims', {})
    cards = []
    for item in items:
        label = labels.get(item['url'])
        if not label or not label.get('claim') or item['url'] in linked:
            continue  # not labeled yet, a roundup that checks no single claim, or shown on its narrative's card
        claim = motif_index.corrected(label['claim'], index)  # a person's correction of the summary, if any
        motifs = motif_cards(index, claim)
        cards.append({'kind': 'checks', 'sources': ['checks'], 'claim': claim, 'title': item['title'], 'url': item['url'],
                      'checker': item['source'], 'date': item['published'][:10], 'politics': bool(label.get('politics')),
                      'rumor_class': label.get('rumor_class') if label.get('rumor_class') != 'other' else None,
                      'conspiracy': (label.get('conspiracy') if label.get('conspiracy') != 'not a conspiracy' else None),
                      'family': label.get('family') if label.get('family') != 'none' else None,
                      'seen': seen.get(item['url']) if looked else None, 'looked_hours': looked.get('hours') if looked else None,
                      'motifs': motifs, 'genres': genres(motifs)})
    return cards


def show_cards(index: dict, screen) -> list[dict]:
    """A card per claim told on two or more shows (or by two callers), as the hourly run last grouped them
    (show_claims.kept_retold): the claim in our words, which shows told it, and how many callers; never the quotes
    or who the callers were"""
    cards = []
    for r in show_claims.kept_retold():
        told = motif_index.corrected(r['claim'], index)
        shown = screen.shown(told, show_claims.SOURCE)
        if not shown:
            continue
        leans = {s['show']: s.get('lean') for s in r.get('told', [])}
        motifs = motif_cards(index, told)
        cards.append({'kind': 'shows', 'sources': ['shows'], 'claim': shown, 'date': r['date'], 'politics': True,
                      'shows': [{'name': s, 'ink': SHOW_INK.get(leans.get(s) or '', '#b8b8c8')} for s in r['shows']],
                      'tellings': r['tellings'], 'callers': (r.get('speakers') or {}).get('caller', 0),
                      'leans': {k: n for k, n in (r.get('leans') or {}).items() if k},
                      'rumor_class': None, 'conspiracy': None, 'family': None, 'motifs': motifs, 'genres': genres(motifs)})
    return cards


def told_before(threads: dict, report: str, claim: str, index: dict) -> list[dict]:
    """The earlier days the same narrative was told (app/analysis/narrative_threads.py), newest first, in our words"""
    thread = narrative_threads.thread_of(threads, report, claim)
    if not thread:
        return []
    return [{'day': date.fromisoformat(d['date']).strftime('%b %-d'), 'people': d['people'],
             'claim': motif_index.corrected(d['claim'], index)}
            for d in reversed(thread['days']) if d['report'] != report]


def latest_report() -> dict | None:
    reports = sorted(glob.glob(os.path.join(FOLDER, 'report-*.json')))
    if not reports:
        return None
    with open(reports[-1]) as f:
        return dict(json.load(f), file=os.path.basename(reports[-1]))


class FolklorePage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('folklore.html')

    def generate(self):
        logger.info("Generating folklore page...")
        report = latest_report()
        cards, copies, fewer = [], [], 0
        bsky = bluesky_examples.prepared()
        pulled = withheld()
        index = motif_index.load()
        threads = narrative_threads.load()
        screen = accusations.screen()  # claims accusing a named private person of a crime: name swapped out, or held
        floor = max(MIN_PEOPLE, round(report['authors'] / PEOPLE_SHARE)) if report else MIN_PEOPLE
        if report:
            for g in report['found']:
                label = g.get('label') or {}
                if label.get('narrative') in pulled:
                    continue
                if label.get('retold') and g['authors'] < floor:
                    fewer += 1
                elif label.get('retold'):
                    claim = motif_index.corrected(label.get('narrative') or '', index)
                    shown = screen.shown(claim)
                    if not shown:
                        continue
                    named = shown == claim  # else its cast, posts and earlier tellings may name the person too
                    motifs = motif_cards(index, claim)
                    cards.append({
                        'kind': 'posts', 'sources': ['posts'] + (['checks'] if g.get('factchecks') else []),
                        'claim': shown, 'people': g['authors'], 'posts': g['posts'],
                        'variety': g['variety'], 'variety_pct': round(100 * g['variety']),
                        'politics': bool(label.get('politics')),
                        # Shown on the site only from evidence (the lean of the outlets its posts share); the
                        # model's guess, unchecked, only in previews
                        'side': g.get('shared_side') or (label.get('side', 'none') if Config.debug else None),
                        'side_from': 'shares' if g.get('shared_side') else 'model',
                        'side_ink': SIDE_INK.get(g.get('shared_side') or label.get('side'), '#8a8f98'),
                        'story_shape': label.get('genre') not in NOT_STORIES,
                        'rumor_class': label.get('rumor_class') if label.get('rumor_class') != 'other' else None,
                        'conspiracy': label.get('conspiracy') if label.get('conspiracy') != 'not a conspiracy' else None,
                        'family': label.get('family') if label.get('family') != 'none' else None,
                        'story': g.get('story'), 'articles': g.get('articles') or [],
                        'factchecks': g.get('factchecks') or [],
                        'motifs': motifs, 'genres': genres(motifs),
                        'examples': g['examples'][:4] if Config.debug and named else [],
                        'bluesky': bluesky_examples.examples(g.get('uris'), bsky) if named else [],
                        'told_before': [{**b, 'claim': c} for b in told_before(threads, report.get('file', ''), label.get('narrative') or '', index)
                                        if (c := screen.shown(b['claim']))],
                    })
                elif g['kind'] == 'copypasta':
                    copies.append({'people': g['authors'], 'posts': g['posts'],
                                   'example': g['examples'][0] if Config.debug else None})
        # What voters say in The Focus Group's episodes, the latest few, in our words (never their quotes), with the
        # motifs each claim is filed under: a source of its own beside the posts
        from app.analysis import focus_group
        voters = []
        for url, ep in sorted(focus_group.load().items(), key=lambda kv: kv[1].get('date', ''), reverse=True)[:FOCUS_EPISODES]:
            said = [{'claim': shown, 'side': c.get('side') or '', 'motifs': motif_cards(index, told)}
                    for c in ep.get('claims', []) if (told := motif_index.corrected(c['claim'], index))
                    and (shown := screen.shown(told, 'Focus Group'))]
            if said:
                voters.append({'title': ep['title'], 'date': ep['date'], 'url': url, 'claims': said})
        # Then what's told on the shows, and the fact-checks no narrative's card links already
        cards += show_cards(index, screen)
        cards += checked_cards(index, {p['url'] for c in cards for p in c.get('factchecks', [])})
        screen.save()
        looked = circulation.load()
        self.template.write({
            'title': 'Folklore and rumors', 'bsky_rule': bluesky_examples.RULE, 'bsky_script': bluesky_examples.SCRIPT,
            'report': report, 'cards': cards, 'copies': copies, 'voters': voters, 'floor': floor, 'fewer': fewer,
            'sources': SOURCES, 'source_counts': counted(cards, 'sources'), 'kinds': Counter(c['kind'] for c in cards),
            'genre_counts': counted(cards, 'genres'), 'family_counts': counted(cards, 'family'),
            'class_counts': counted(cards, 'rumor_class'), 'scope_counts': counted(cards, 'conspiracy'),
            'rumor_classes': RUMOR_CLASSES, 'conspiracy_scopes': CONSPIRACY_SCOPES, 'shape_emoji': SHAPE_EMOJI,
            'motif_counts': motif_counts(cards), 'with_motifs': sum(bool(c['motifs']) for c in cards),
            'looked': looked, 'seen_count': sum(1 for c in cards if (c.get('seen') or {}).get('people')),
            'check_days': CHECK_DAYS, 'checkers': sorted({c['checker'] for c in cards if c['kind'] == 'checks'}),
            'preview': Config.debug,
        })
        # The Rumors page was folded in here (Oct 8): its address opens this one on the fact-checks
        with open(os.path.join(Config.build, 'rumors.html'), 'w', encoding='utf-8') as f:
            f.write(MOVED.format(to='folklore.html#checks'))
        logger.info("...%d cards (%s), %d copypasta groups", len(cards),
                    ', '.join(f'{n} {k}' for k, n in Counter(c['kind'] for c in cards).items()), len(copies))
