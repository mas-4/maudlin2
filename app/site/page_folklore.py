"""Folklore (work in progress, #142): the folklore-shaped narratives in what people say on Bluesky and Mastodon, from the
latest nightly report (app/narratives.py). A card per retold narrative: the claim in the model's words, how many
people tell it and how varied their wording is, its genre and Motif-Index motif, and the news story it rides
on.

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
from app.analysis import accusations, motif_index, narrative_threads
from app.site.common import TemplateHandler
from app.utils import Config, get_logger
from app.utils.store import read_json

logger = get_logger(__name__)

FOLDER = os.path.join(Config.data, 'narratives')
GENRE_EMOJI = {'rumor': '🗣️', 'contemporary legend': '🏙️', 'conspiracy theory': '🕸️', 'folk belief': '🔮',
               'prophecy or prediction': '🔭', 'cautionary tale': '⚠️', 'atrocity story': '🩸', 'trickster tale': '🦊',
               'joke formula or meme': '🤡', 'proverb or catchphrase': '📜', 'personal testimony': '🙋',
               'news report or shared reaction': '📣'}
# Fewer tellers than this aren't shown: at five to nine people (half of what the finder keeps) most groups are a
# handful reacting to the same news, not a story people retell. The floor grows with the sample, 1 in PEOPLE_SHARE.
MIN_PEOPLE = 10
PEOPLE_SHARE = 2500
# Plain glosses, in our words, of what each Motif-Index chapter covers (shown on hover and in "What the labels mean")
CHAPTER_NOTES = {
    'A': 'creators, gods, and how the world began or will end', 'B': 'talking, helpful or monstrous animals',
    'C': 'forbidden acts and what happens to people who break the rule',
    'D': 'transformations, enchantments, magic objects and powers', 'E': 'ghosts, the soul, returns from the dead',
    'F': 'wonders, other worlds, extraordinary beings and places', 'G': 'monsters, witches and other menaces',
    'H': 'trials of identity, wit, strength or worth', 'J': 'cleverness and stupidity, good and bad judgment',
    'K': 'tricks, disguises, frauds, hidden plots and false appearances',
    'L': 'the lowly raised up, the proud brought down', 'M': 'oaths, bargains, curses and prophecies',
    'N': 'luck, accidents and fate', 'P': 'rulers, classes, families, trades and customs',
    'Q': 'deeds paid back, rewarded or punished', 'R': 'captures, rescues and escapes',
    'S': 'cruel relatives, murders, abandonment and sacrifice', 'T': 'love, marriage, seduction and birth',
    'U': 'how life and the world work', 'V': 'worship, saints, religious belief and practice',
    'W': 'virtues and vices', 'X': 'jokes about kinds of people, absurd lies',
    'Z': 'formulas, symbols, numbers and other patterns',
}
GENRE_NOTES = {
    'rumor': 'an unconfirmed claim passed along as news ("I heard that…")',
    'contemporary legend': 'a story told as true and recent, often about a friend of a friend (the folklorists\' '
                           'name for an "urban legend")',
    'conspiracy theory': 'a hidden group said to be secretly behind events',
    'folk belief': 'something held as known without evidence, often about health, luck or how the world works',
    'prophecy or prediction': "what's going to happen",
    'cautionary tale': 'a story told as a warning',
    'atrocity story': "a story of shocking cruelty by the other side, told to show what they're like",
    'trickster tale': 'a clever figure outwitting the powerful',
    'joke formula or meme': 'a joke shape people refill with new content',
    'proverb or catchphrase': 'a stock saying or slogan repeated as wisdom',
    'personal testimony': 'many people telling the same kind of experience as their own',
    'news report or shared reaction': 'many people passing on, or reacting to, the same news; not folklore in '
                                      'itself, kept for comparison',
}
NOT_STORIES = {'news report or shared reaction', 'none: a shared topic, not a retold narrative'}  # no cast or motif
SIDE_INK = {'left': '#1a5cff', 'right': '#e0102e', 'both': '#7a3fd1', 'none': '#8a8f98'}


WITHHELD = os.path.join(FOLDER, 'withheld.json')  # narratives pulled by hand: [{claim, reason, at}]


def withheld() -> set[str]:
    """Claims withheld from the page by hand after a misreading (Oct 4: a group of trans people talking about their
    own identity was labeled as spreading an anti-trans claim one of them had quoted)."""
    return {w['claim'] for w in read_json(WITHHELD, [])}


FOCUS_EPISODES = 4  # Focus Group episodes shown, the latest
MOTIF_CHIPS = 12  # motif filters at most


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
    return [{'id': e['id'], 'name': e['name'], 'count': len(motif_index.public_claims(e)), 'note': motif_index.public_note(e)}
            for e in (motif_index.entries_of(index, claim) if claim else [])
            if motif_index.public(e) and k in set(e.get('done') or [])]


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
                    cards.append({
                        'claim': shown, 'people': g['authors'], 'posts': g['posts'],
                        'variety': g['variety'], 'variety_pct': round(100 * g['variety']),
                        'genre': label.get('genre', ''), 'genre_emoji': GENRE_EMOJI.get(label.get('genre'), '🧶'),
                        'chapter': '' if label.get('motif_chapter') in (None, '', 'none') else label['motif_chapter'],
                        'motif': label.get('motif', ''),
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
                        'motifs': motif_cards(index, motif_index.corrected(label.get('narrative') or '', index)),
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
        screen.save()
        self.template.write({
            'title': 'Folklore', 'bsky_rule': bluesky_examples.RULE, 'bsky_script': bluesky_examples.SCRIPT,
            'report': report, 'cards': cards, 'copies': copies, 'voters': voters,
            'floor': floor, 'fewer': fewer, 'genres': Counter(c['genre'] for c in cards).most_common(), 'genre_emoji': GENRE_EMOJI,
            'genre_notes': GENRE_NOTES, 'chapter_notes': CHAPTER_NOTES,
            'rumor_classes': RUMOR_CLASSES, 'conspiracy_scopes': CONSPIRACY_SCOPES, 'shape_emoji': SHAPE_EMOJI,
            'class_counts': Counter(c['rumor_class'] for c in cards if c['rumor_class']).most_common(),
            'scope_counts': Counter(c['conspiracy'] for c in cards if c['conspiracy']).most_common(),
            'chapters_seen': sorted({c['chapter'] for c in cards if c['chapter']}),
            'motif_counts': motif_counts(cards), 'with_motifs': sum(bool(c['motifs']) for c in cards),
            'preview': Config.debug,
        })
        logger.info("...%d narratives, %d copypasta groups", len(cards), len(copies))
