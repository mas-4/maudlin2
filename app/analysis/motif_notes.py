"""The model's drafts of a motif's scope note, genre and groups (split from motif_index.py on Oct 21, Fable's
architecture review): drafted for new motifs in the nightly run and shown in the workbench to keep or edit. Reached as
before through motif_index (mi.gloss, mi.gloss_missing)."""
import re
from datetime import datetime as dt


from app.analysis import llm
from app.utils import get_logger
from app.analysis import motif_index as mi

logger = get_logger(__name__)


GLOSS_PROMPT = """A motif in our index of recurring rumor and narrative shapes: {name}
Claims people are telling that are filed under it:
{claims}

common: first, in a sentence or two, what these claims have in common as stories: who does what to whom, as the \
people telling them tell it. Look past the particular events to the kind of story. The motif's name is the main \
guide (a person chose many of them): with only one or two claims, take the kind of story from the name, and use the \
claims only to see how it is told.
note: then the motif's scope note: one plain sentence saying what kind of story this motif covers, built from what \
they have in common. Write it the way its tellers tell it, as if it were so; never judge it (no "false", \
"misleading", "debunked", "claims that" or "alleged"). Use kinds of people and places, not particular ones, unless \
the motif's own name names them: then it is a named narrative, and the note keeps that name. Start with what \
happens, not with the motif's name, "This motif", "A motif" or "Stories"."""
GLOSS_SCHEMA = {"type": "object", "properties": {"common": {"type": "string", "maxLength": 500},
                                                 "note": {"type": "string", "maxLength": 320}},
                "required": ["common", "note"]}
GLOSS_CLAIMS = 8  # claims shown when drafting a note
# Oct 6, drafts for the 49 motifs whose notes a person wrote, compared with theirs: gemma4:26b drafted all 49, closest
# to the person's (0.73 by meaning), describing the kind of story; qwen3:30b-a3b gave up on 10 (judged or named
# people three times) and restated single claims (0.71)
GLOSS_MODEL = 'gemma4:26b'
GLOSS_MIN = 3  # claims a motif needs before the model drafts its note: with one or two it restated them (Oct 5)


VERDICT_WORDS = re.compile(r"\b(false|falsely|misleading|debunked|unfounded|baseless|claims? that|alleged(ly)?|"
                           r"misinformation|disinformation|conspiracy theor)", re.I)


def gloss(entry: dict) -> str | None:
    """The model's draft of a motif's scope note, from its name and claims: the story as its tellers tell it. A draft
    that judges the story (fact-check summaries pull it toward "falsely attributed") or names people or places is
    asked for again, twice at most, then left for a person. Motifs whose names are themselves about falsehood (Fake news) may say so: their name is the story."""
    claims = '\n'.join(f'- {c["claim"][:180]}' for c in entry['claims'][-GLOSS_CLAIMS:]) or '(none yet)'
    prompt = GLOSS_PROMPT.format(name=entry['name'], claims=claims)
    about_falsehood = re.search(r'\b(fake|false|lie|lies|hoax|disinformation|misinformation|propaganda)\b', entry['name'], re.I)
    for _attempt in range(3):
        answer = llm.complete_json(prompt, GLOSS_SCHEMA, max_tokens=600, model=GLOSS_MODEL)
        note = ' '.join((answer or {}).get('note', '').split())
        if not note or note[-1] not in '.!?"\u201d':
            continue  # none, or cut off at the length limit mid-sentence
        if re.search(r'\b(the user|scope note|motif)\b', note, re.I):
            continue  # the model talking about the task, not answering it
        judged = VERDICT_WORDS.search(note) and not about_falsehood
        own = {w.lower() for w in re.findall(r"[\w'-]+", entry['name'])}  # a named narrative keeps its names
        named = [w for w in names_in(note) if w.lower() not in own]
        # A draft opening with the motif's own name ("Breaking ranks occurs when...") defines a word instead of telling
        # what happens (17 of 49 Gemma drafts did, Oct 6)
        echoed = note.lower().startswith(entry['name'].lower())
        if not judged and not named and not echoed:
            return note
        prompt += ('\n\nYour last answer: "' + note + '". ' + ('It judged the story: say only what the people telling '
                   'it say happens. ' if judged else '') + (f'It named {", ".join(named)}: say what they are instead. '
                                                            if named else '')
                   + ('It began with the motif\'s name: begin with who does what instead.' if echoed else ''))
    return None


def names_in(text: str) -> list[str]:
    """Capitalized words past the first that aren't sentence starts: names, which a scope note shouldn't have"""
    words = re.findall(r"[A-Za-z][\w'-]*", text)
    return [w for i, w in enumerate(words[1:], 1) if w[0].isupper() and w not in ('I',)
            and not re.search(r'[.!?]\s+' + re.escape(w), text)]


def needs_gloss(entry: dict) -> bool:
    """A motif with GLOSS_MIN claims and no note, or a model draft from when it held half as many claims or fewer.
    A person's note (written or kept) is never redrafted."""
    n = len(entry['claims'])
    if n < GLOSS_MIN:
        return False
    if not entry.get('note'):
        return True
    return entry.get('note_by') == 'model' and n >= 2 * entry.get('note_claims', n)


def needs_drafts(entry: dict) -> bool:
    """A motif the model made that nobody has looked over and the model hasn't drafted for yet"""
    return bool(entry['claims']) and not entry.get('curated') and 'done' not in entry and not entry.get('drafted')


def draft_missing(budget: float | None = None) -> int:
    """The model's note, genre and groups for each motif it made since the last run (needs_drafts), for at most
    `budget` seconds, each only where the motif has none; how many motifs got drafts"""
    import time

    from app.analysis import motif_proposals as mp
    started, done = time.time(), 0
    index = mi.load()
    todo = [e['id'] for e in mi.live(index) if needs_drafts(e)]
    if not todo:
        return 0
    examples = mp.genre_examples(index)
    for eid in todo:
        if budget is not None and time.time() - started > budget:
            break
        entry = mi.load()['entries'][eid]
        note = None if entry.get('note') else gloss(entry)
        drafted = dict(entry, note=note or entry.get('note', ''))
        genre = None
        if not mi.genre_of(entry) and len(examples) >= 2:
            got = mp.ask_genre(drafted, examples, mi.facet_notes(index).get('genre'))
            genre = got and got[0]
        groups = [] if mi.groups_of(entry) else mp.ask_groups(drafted, index)
        with mi.locked():
            index = mi.load()
            e = index['entries'].get(eid)
            if not e or not needs_drafts(e):
                continue  # a person got there first
            if note and not e.get('note'):
                e['note'], e['note_by'], e['note_claims'] = note, 'model', len(e['claims'])
            if genre and not mi.genre_of(e):
                e.setdefault('facets', {})['genre'] = genre
                mi._drafts(e, genre=genre)
            if groups and not mi.groups_of(e):
                mi._set_groups(e, groups)
                mi._drafts(e, groups=groups)
            e['drafted'] = dt.now().strftime('%Y-%m-%d')
            mi.save(index)
            done += 1
    if done:
        logger.info("Motif index: drafted note, genre and groups for %d new motifs", done)
    return done


def gloss_missing(budget: float | None = None) -> int:
    """Draft notes for the motifs that need one (needs_gloss), for at most `budget` seconds; how many were drafted"""
    import time
    started, done = time.time(), 0
    for eid in [e['id'] for e in mi.live(mi.load()) if needs_gloss(e)]:
        if budget is not None and time.time() - started > budget:
            break
        entry = mi.load()['entries'][eid]
        note = gloss(entry)
        if not note:
            continue
        with mi.locked():
            index = mi.load()
            e = index['entries'].get(eid)
            if e and needs_gloss(e):  # a person may have written one meanwhile
                e['note'], e['note_by'], e['note_claims'] = note, 'model', len(e['claims'])
                mi.save(index)
                done += 1
    if done:
        logger.info("Motif index: drafted %d scope notes", done)
    return done
