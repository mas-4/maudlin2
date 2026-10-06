"""What the shows, newsletters, streams and investigations beyond the front pages talk about: the model tags each
item (its title and summary) with one to three subjects from a fixed list, so they can be read by subject on the
"Beyond the front pages" page instead of as a list of links. Tags are kept per item (they don't change)."""
import os

from app.analysis import llm
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

TAGS = os.path.join(Config.data, 'subject_tags.json')  # url -> [subjects]
MAX_NEW = 80  # model calls a run, at most
SUBJECTS = ['elections and campaigns', 'Congress and legislation', 'the White House and the presidency',
            'courts and the law', 'immigration', 'the economy and jobs', 'taxes and government spending',
            'health and medicine', 'crime and policing', 'guns', 'abortion and reproductive rights',
            'race and civil rights', 'gender and sexuality', 'religion', 'education', 'climate and energy',
            'technology and AI', 'media and the press', 'foreign policy and war', 'Israel and Gaza',
            'Russia and Ukraine', 'China', 'the Middle East', 'Europe', 'Latin America', 'Asia', 'Africa',
            'national security and the military', 'corruption and scandal', 'conspiracy theories and disinformation',
            'culture and entertainment', 'sports', 'science', 'history', 'other']
# An emoji and a capitalized label for each subject, for its tag on the page
EMOJI = {'elections and campaigns': '🗳️', 'Congress and legislation': '🏛️', 'the White House and the presidency': '🦅',
         'courts and the law': '⚖️', 'immigration': '🛂', 'the economy and jobs': '💼', 'taxes and government spending': '💸',
         'health and medicine': '🩺', 'crime and policing': '🚓', 'guns': '🔫', 'abortion and reproductive rights': '🤰',
         'race and civil rights': '✊', 'gender and sexuality': '🏳️‍🌈', 'religion': '🙏', 'education': '🎓',
         'climate and energy': '🌍', 'technology and AI': '🤖', 'media and the press': '📰', 'foreign policy and war': '🌐',
         'Israel and Gaza': '🕊️', 'Russia and Ukraine': '🪖', 'China': '🐉', 'the Middle East': '🕌', 'Europe': '🇪🇺',
         'Latin America': '🌎', 'Asia': '🌏', 'Africa': '🌍', 'national security and the military': '🛡️',
         'corruption and scandal': '💰', 'conspiracy theories and disinformation': '🕵️', 'culture and entertainment': '🎬',
         'sports': '🏟️', 'science': '🔬', 'history': '📜', 'other': '🏷️'}


def label(subject: str) -> str:
    """'the White House and the presidency' -> 'The White House and the presidency'"""
    return subject[:1].upper() + subject[1:]


PROMPT = """A piece from {source}:
{title}
{summary}

What is it about? Give its main subject from this list. Add a second or third only if the title or summary \
plainly discusses that too; most pieces have one. If the title and summary don't say what it's about (a teaser like \
"You won't believe this"), answer "other". Subjects: {subjects}"""
SCHEMA = {"type": "object", "properties": {"subjects": {"type": "array", "minItems": 1, "maxItems": 3,
                                                        "items": {"type": "string", "enum": SUBJECTS}}},
          "required": ["subjects"]}


def load() -> dict:
    return read_json(TAGS, {})


def tag(items: list[dict], limit: int = MAX_NEW) -> dict:
    """url -> its subjects, tagging the items that have none yet (at most `limit` model calls)."""
    tags = load()
    todo = [i for i in items if i.get('url') and i['url'] not in tags][:limit]
    if todo and llm.backend() is not None:
        for item in todo:
            answer = llm.complete_json(PROMPT.format(source=item.get('source', ''), title=item.get('title', ''),
                                                     summary=(item.get('summary') or '')[:400],
                                                     subjects='; '.join(SUBJECTS)), SCHEMA, max_tokens=60)
            if answer:
                tags[item['url']] = list(dict.fromkeys(answer['subjects']))
        write_json(TAGS, tags)
        logger.info("Subjects: tagged %d new items (%d in all)", len(todo), len(tags))
    return tags
