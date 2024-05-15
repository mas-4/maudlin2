import re

import pandas as pd
from bs4 import BeautifulSoup as Soup, NavigableString
from sqlalchemy import update, delete

from app.models import Session, Headline
from app.utils.logger import get_logger

logger = get_logger(__name__)

REPLACEMENTS: dict[str, str] = {
    # smart quotes
    "“": '"',
    "”": '"',
    "’": "'",
    "‘": "'",
    # long dashes
    "—": "--",
    "–": "--",
    "−": "--",
    'Just now': '',
    r'updated \d+[Mm] ago': ' ',
    r'about \d+ hours? ago': ' ',
    r"updated \d+[Hh] ago": " ",
    r'posted \d+ hours? ago': ' ',
    r'posted \d+ minutes? ago': ' ',
    r'\d+[Mm] ago': ' ',
    r'\d+[Hh] ago': ' ',
    r'\d+ hours? ago': ' ',
    r'\d+ minutes? ago': ' ',
    r'\d+ hrs? ago': ' ',
    r'\d+ days? ago': ' ',
    r'\d+ mins? ago': ' ',
    "<br>": " ",
    "<br/>": " ",
    "<br />": " ",
    '\xad': ' ',
    '\xa0': ' ',
    '\n': ' ',
    '\t': ' ',
    '\r': ' ',
    r'\s+': ' ',
}


def remove_stops(headline):
    for pat, repl in REPLACEMENTS.items():
        headline = re.sub(pat, repl, headline)
    return headline


PATRONYMS: list[str] = ["mc", "mac", "van", "von", "de", "la", "le", "el", "al", "di", "da", "du", "del", "della",
                        "delle", "delli", "dello"]
WHITELIST: list[str] = ["mRNA", ".com", ".io", ".net", ".org", ".gov", ".edu", ".mil", ".int", ".tv", ".uk", ".us",
                        ".uk", "iPhone", "U.S.", "U.S.A.", "U.K.", "TikTok"]


def split_camelcases(text):
    text = text.split()
    for i, word in enumerate(text):
        if word in WHITELIST or any(w in word for w in WHITELIST):
            continue
        split = re.sub(r'([a-z])([A-Z])', r'\1 \2', word).split()
        if split[0].lower() in PATRONYMS:
            continue
        # splitting camel case
        text[i] = ' '.join(split)
        # split '?!.,' from the word
        text[i] = re.sub(r'([?!.:;,])([a-zA-Z])', r'\1 \2', text[i])
    return ' '.join(text)


def strip_story_attributions(text):
    if text.endswith("/Getty Images") and len(text.split()) == 3:  # "First Last/Getty Images"
        return ""
    if text.endswith("/ AP") and len(text[:-len("/ AP")].strip().split()) == 2:  # "First Last / AP"
        return ""
    if text.startswith("Reuters/") and len(text.split()) == 2:  # "Reuters/First Last"
        return ""
    return text


def preprocess(text: str):
    if not (text := strip_story_attributions(text)):
        return ""
    text = remove_stops(text)
    return text.strip('.').strip()


def legacy_preprocess(text: str):
    """
    This is used for legacy headlines where we don't properly parse tags.

    We have this as an entirely separate function so we can skip boolean checks. For speed!
    """
    if not (text := strip_story_attributions(text)):
        return ""
    text = remove_stops(text)
    text = split_camelcases(text)
    return text.strip('.').strip()


def strip_ie_conditionals(html_content):
    return re.sub(r'\[if.*?\].*\[endif\]', '', html_content, flags=re.DOTALL)  # noqa


def strip_raw_json(html_content):
    return re.sub(r'\{.*?\}', '', html_content, flags=re.DOTALL)  # noqa


def extract_text(html_content):
    soup = Soup(str(html_content), 'html.parser')

    stack = [soup]

    def generate_text_elements(_stack):
        while _stack:
            current_element = _stack.pop()
            if isinstance(current_element, NavigableString):
                # I have wondered if we could use a list comp here to speed up this processing. Otherwise perhaps
                # we could just eventually write some CPython. If we go beyond 2 maybe.
                if '[' in current_element:
                    current_element = strip_ie_conditionals(current_element)
                if '{' in current_element:
                    current_element = strip_raw_json(current_element)
                yield current_element.replace('\\n', '').strip()
            else:
                _stack.extend(reversed(list(current_element.children)))

    return ' '.join(list(generate_text_elements(stack)))


cols = ['id', 'processed', 'first_accessed', 'last_accessed', 'legacy', 'title']


def deduplicate(df):
    # Take the first first_accessed and last last_accessed for each duplicate set of titles
    # create a df of updates that contains the id, processed, first_accessed, and last_accessed of the duplicates
    # create a list of deletes that contains the id of the duplicates that we're not keeping
    updates = []
    deletes = []
    for title, group in df.groupby('processed'):
        if len(group) == 1:
            continue
        keep = group.sort_values('first_accessed').iloc[0]
        # update keep last_accessed with the max of the group
        keep['last_accessed'] = group['last_accessed'].max()
        updates.append(keep[cols])
        deletes.extend(group[~group['id'].eq(keep['id'])]['id'])
    if updates:
        updates = pd.concat(updates, axis=1).T.to_dict(orient='records')
    deletes = list(set(deletes))
    return updates, deletes


def reprocess_headlines(all_headlines: bool = False):
    df = get_headlines(all_headlines)

    logger.info("Processing %i headlines", len(df))
    if len(df) == 0:
        return

    # Mark where the raw column is empty as legacy headlines
    df['legacy'] = df['raw'].isnull()

    # We have to extract the text from the raw html for non-legacy
    logger.info("Extracting text...")
    df['processed'] = ''
    df.loc[~df['legacy'], 'processed'] = df[~df['legacy']]['raw'].apply(extract_text)
    logger.info("Preprocessing text...")
    df.loc[~df['legacy'], 'processed'] = df[~df['legacy']]['processed'].apply(preprocess)
    logger.info("Preprocessing legacy text...")
    df.loc[df['legacy'], 'processed'] = df[df['legacy']]['title'].apply(legacy_preprocess)

    # Convert legacy to bool, 0 is False, 1 is True
    df['legacy'] = df['legacy'].astype(int)

    # get the ids of empty processed headlines
    empty: list[int] = df[df['processed'] == '']['id'].tolist()
    df = df[df['processed'] != '']

    # drop the empty headlines
    logger.info("Deduplicating...")
    updates, deletes = deduplicate(df)
    deletes.extend(empty)

    # drop all deletes from df
    df = df[~df['id'].isin(deletes)]

    # drop all updates from df
    df = df[~df['id'].isin([u['id'] for u in updates])]

    # add remaining from df to updates
    updates.extend(df[cols].to_dict(orient='records'))

    # NOTE: We're updating the title on both legacy and non-legacy headlines
    # This is technically a big no no since the title is the raw original content for legacy headlines
    # HOWEVER: since we didn't change the legacy title in the dataframe (please review code above carefully) we
    # can safely update the title for legacy headlines as well. It just simplifies this code, though it might slow it

    with Session() as s:
        stride = 998
        if len(updates):
            logger.info("Updating %i headlines", len(updates))
            for i in range(0, len(updates), stride):
                s.execute(update(Headline), updates[i:i + stride])
        if len(deletes):
            logger.info("Deleting %i headlines", len(deletes))
            for i in range(0, len(deletes), stride):
                s.execute(delete(Headline).where(Headline.id.in_(deletes[i:i + stride])))
        s.commit()
    logger.info("Headline reprocessing complete")


def get_headlines(all_headlines):
    query_cols = {
        "id": Headline.id,
        "raw": Headline.raw,
        "title": Headline.title,
        "first_accessed": Headline.first_accessed,
        "last_accessed": Headline.last_accessed,
    }
    with Session() as s:
        if all_headlines:
            headlines = s.query(*list(query_cols.values())).all()
        else:
            headlines = s.query(*list(query_cols.values())).filter(Headline.processed == None).all()  # noqa None comparison
    return pd.DataFrame(headlines, columns=[*query_cols.keys()])


if __name__ == '__main__':
    reprocess_headlines(True)
