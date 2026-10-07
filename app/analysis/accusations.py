"""Claims that accuse a named person of a crime, held back from the published site (Oct 6).

The site shows what people online retell, and what voters say in The Focus Group, in our words: "Jacob Geller is a
rapist who has avoided accountability…" reached the motif index, a story page and a saga page, an unverified
accusation of a serious crime against someone named who holds no public office. Before any such claim is shown, the
bigger local model reads it: does it say or imply that a person it names committed a crime or sexual or violent
abuse? A person who holds or held public office, is running for it, or is a household name (Elon Musk, Sean Combs)
stays named: what's said about them is political and celebrity folklore, the site's own subject, and they're in the
news every day. So does anyone our outlets' front-page headlines have named in IN_THE_NEWS articles or more, whatever
the model knows of them (it didn't know Howard Lutnick is in the cabinet; Christa Pike's execution was on 284). Anyone else, known only within a niche (most YouTubers and streamers, local figures) or not at all,
is replaced by a generic description of who they are ("a YouTuber"). If the name can't be swapped out cleanly, or
the claim hasn't been read yet, it isn't shown at all.

Anything that slips through goes on the blacklist (NEVER_NAMED, kept by hand): those names are swapped out of every
claim the site shows, whatever the model said. Its opposite, ALWAYS_NAMED, is for public people the model and the
headlines miss (a small-time politician): never swapped out.

Claims a fact-checker examined (on the Rumors page) are shown as the fact-checker wrote them: they have been checked.
The checker (local, never published) always shows claims as told."""
import re

from app.analysis import llm
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

import hashlib
import os

logger = get_logger(__name__)

CACHE = os.path.join(Config.data, 'accusations.json')  # claim key -> what the model said
NEVER_NAMED = os.path.join(Config.data, 'never_named.json')  # by hand: {"Jacob Geller": "a YouTuber", ...}
ALWAYS_NAMED = os.path.join(Config.data, 'always_named.json')  # by hand: ["Don Huffines", ...]
MODEL = 'gemma4:26b'
IN_THE_NEWS = 3  # front-page articles whose headlines name a person for them to stay named
PER_BUILD = 40  # claims read in one build at most; the rest are held back until a later one reads them
FACT_CHECKERS = {'Snopes', 'Lead Stories', 'PolitiFact', 'NewsGuard Reality Check', 'Full Fact', 'FactCheck.org',
                 'AFP Fact Check', 'Reuters Fact Check', 'AP Fact Check', 'Science Feedback'}
PROMPT = """A claim people are telling online: {claim}

Does it say or imply that a particular person, named in it, committed a crime, or sexual or violent abuse (rape, \
assault, abuse of children, murder, fraud, theft, bribery, trafficking and the like)? Insults, opinions, bad \
character, rude or offensive words and legal but unethical acts are not crimes. Only people named by their own \
personal name count: not groups or group nicknames ("the Cornell 7"), companies, governments or unnamed people. List \
each such person; an empty list if none.

For each:
crime: the crime or abuse the claim says they committed, in a few words
names: every way the claim names them, exactly as written in it ("Jacob Geller", "Geller")
who: a short generic description of who they are, with no name, that fits in the sentence in their place \
("a YouTuber", "a businessman", "a fraternity member")
well_known: true if they hold or held public office or are running for it (a president, member of Congress, \
governor, mayor, judge, cabinet member, appointed official, candidate), or are a household name most American adults \
would know (Elon Musk, Sean Combs, Taylor Swift); false for people known mainly within a niche (most YouTubers, \
streamers, podcasters, local figures) and private people"""
SCHEMA = {"type": "object", "properties": {"accused": {"type": "array", "maxItems": 6, "items": {
    "type": "object", "properties": {"crime": {"type": "string", "maxLength": 80},
                                     "names": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 4},
                                     "who": {"type": "string", "maxLength": 60},
                                     "well_known": {"type": "boolean"}},
    "required": ["crime", "names", "who", "well_known"]}}}, "required": ["accused"]}


def key(claim: str) -> str:
    return hashlib.sha1(' '.join(claim.split()).lower().encode()).hexdigest()[:16]


def read(claim: str) -> dict | None:
    answer = llm.complete_json(PROMPT.format(claim=claim), SCHEMA, max_tokens=400, model=MODEL)
    return {'accused': answer['accused']} if answer and isinstance(answer.get('accused'), list) else None


PARTICLES = {'de', 'da', 'di', 'del', 'van', 'von', 'der', 'bin', 'al', 'el', 'la', 'le', 'du', 'dos', 'jr', 'jr.'}


def personal(name: str) -> bool:
    """Whether a name the model gave is a person's name (capitalized words), not a group's ("the Cornell 7")"""
    words = name.split()
    return bool(words) and all(w[:1].isupper() or w.lower() in PARTICLES for w in words) and not any(
        c.isdigit() for c in name)


NO_CRIME = {'n/a', 'na', 'nothing', 'unspecified', 'unknown'}


def headlines_naming(name: str) -> int:
    """How many front-page articles' headlines name them"""
    from app.models import Headline, Session
    from sqlalchemy import func
    with Session() as s:
        return s.query(func.count(func.distinct(Headline.article_id))).filter(Headline.title.contains(name)).scalar() or 0


def redacted(claim: str, verdict: dict, in_news=lambda name: False) -> str | None:
    """The claim as the site may show it: unchanged, with each accused private person replaced by who they are, or
    None when a name can't be found to replace, or is still there after. `in_news(name)`: whether the news names them
    enough that they stay named."""
    text = claim
    for person in verdict.get('accused') or []:
        crime = (person.get('crime') or '').strip().lower().rstrip('.')
        if person.get('well_known') or not crime or crime in NO_CRIME or crime.startswith(('none', 'no ', 'not ')):
            continue
        names = sorted({n.strip() for n in person.get('names') or [] if personal(n.strip())}, key=len, reverse=True)
        if not names and any(n.strip() for n in person.get('names') or []):
            continue  # a group, not a person
        who = ' '.join((person.get('who') or '').split()) or 'someone'
        if not names or any(n not in text for n in names[:1]):
            return None
        if in_news(names[0]):
            continue
        for n in names:
            text = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)", who, text)
        # "A Chinese national, Wanying Zhang, was…" -> "A Chinese national, a Chinese national, was…": once is enough
        text = re.sub(rf"({re.escape(who)}),\s*{re.escape(who)}(?!\w),?", r"\1", text, flags=re.I)
        words = {w for n in names for w in re.findall(r"[A-Z][\w'-]+", n) if len(w) > 2}
        if any(re.search(rf'(?<!\w){re.escape(w)}(?!\w)', text) for w in words):
            return None  # a name left in (a surname on its own the model didn't list): hold it back
    return text[:1].upper() + text[1:] if text != claim else claim


def blacklisted(text: str, names: dict) -> str:
    """The text with each blacklisted name, and its surname on its own, replaced by who they are"""
    for name, who in sorted(names.items(), key=lambda kv: -len(kv[0])):
        for n in dict.fromkeys([name, name.split()[-1]]):
            if len(n) > 2:
                text = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)", who, text)
    return text[:1].upper() + text[1:]


class Screen:
    """One build's reader: shown(claim) is the claim to publish, or None. Claims not read before are read now, up to
    PER_BUILD; the cache is saved by save()."""

    def __init__(self, read_new: int | None = None, reader=None):
        self.cache = read_json(CACHE, {})
        self.never = read_json(NEVER_NAMED, {})
        self.named = {}  # name -> headlines naming them, this build
        self.always = set(read_json(ALWAYS_NAMED, []))
        self.left = PER_BUILD if read_new is None else read_new
        self.reader = reader
        self.changed = False
        self.held = 0

    def verdict(self, claim: str) -> dict | None:
        k = key(claim)
        if k not in self.cache and self.left > 0:
            self.left -= 1
            v = (self.reader or read)(claim)
            if v is not None:
                self.cache[k] = {**v, 'claim': claim}
                self.changed = True
        return self.cache.get(k)

    def shown(self, claim: str, source: str = 'narrative') -> str | None:
        if source in FACT_CHECKERS or not claim:
            return claim
        v = self.verdict(claim)
        out = redacted(claim, v, self.in_news) if v is not None else None
        if out and self.never:
            out = blacklisted(out, self.never)
        self.held += out is None
        return out

    def in_news(self, name: str) -> bool:
        if name in self.always:
            return True
        if name not in self.named:
            try:
                self.named[name] = headlines_naming(name)
            except Exception as e:  # noqa: no database: the model's word stands
                logger.warning("Accusations: couldn't count headlines naming %s (%s)", name, e)
                self.named[name] = 0
        return self.named[name] >= IN_THE_NEWS

    def changes(self, claim: str, source: str = 'narrative') -> bool:
        """Whether the claim isn't shown as told (held back or a name swapped out): its posts aren't shown either"""
        return self.shown(claim, source) != claim

    def save(self):
        if self.changed:
            write_json(CACHE, self.cache)
            self.changed = False


_screen = None


def screen() -> Screen:
    """The build's one Screen"""
    global _screen
    if _screen is None:
        _screen = Screen()
    return _screen


def shown(claim: str, source: str = 'narrative') -> str | None:
    s = screen()
    out = s.shown(claim, source)
    s.save()
    return out
