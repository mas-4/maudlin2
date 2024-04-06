from app.models import Session, Headline
import pandas as pd
from sqlalchemy import update, delete
import re
from app.utils.logger import get_logger

logger = get_logger(__name__)

replacements: dict[str, str] = {
    # smart quotes
    "“": '"',
    "”": '"',
    "’": "'",
    "‘": "'",
    # long dashes
    "—": "--",
    "–": "--",
    "−": "--",
    r"\d+[Hh]": "",
    "ago": "",
    "AGO": "",
    "<br>": " ",
    "<br/>": " ",
    "<br />": " ",
    "  +": " ",
}

def initial_cleaning(headline):
    for pat, repl in replacements.items():
        headline = re.sub(pat, repl, headline)
    return headline.strip()

def deduplicate(df):
    # Take the first first_accessed and last last_accessed for each duplicate set of titles
    # create a df of updates that contains the id, processed, first_accessed, and last_accessed of the duplicates
    # create a df of deletes that contains the id of the duplicates that we're not keeping
    updates = []
    deletes = []
    for title, group in df.groupby('processed'):
        if len(group) == 1:
            continue
        keep = group.sort_values('first_accessed').iloc[0]
        # update keep last_accessed with the max of the group
        keep['last_accessed'] = group['last_accessed'].max()
        updates.append(keep[['id', 'processed', 'first_accessed', 'last_accessed']])
        deletes.extend(group[~group['id'].eq(keep['id'])]['id'])
    updates = pd.concat(updates, axis=1).T.to_dict(orient='records')
    deletes = list(set(deletes))
    return updates, deletes


def reprocess_headlines(all_headlines: bool = False):
    df = get_headlines(all_headlines)
    logger.debug("Processing %i headlines", len(df))
    if len(df) == 0:
        return
    df['processed'] = df['title'].apply(initial_cleaning)
    updates, deletes = deduplicate(df)
    with Session() as s:
        if len(updates):
            logger.debug("Updating %i headlines", len(updates))
            s.execute(update(Headline), updates)
        if len(deletes):
            logger.debug("Deleting %i headlines", len(deletes))
            s.execute(delete(Headline).where(Headline.id.in_(deletes)))
        s.commit()
    logger.debug("Headline reprocessing complete")


def get_headlines(all_headlines):
    cols = {
        "id": Headline.id,
        "title": Headline.title,
        "first_accessed": Headline.first_accessed,
        "last_accessed": Headline.last_accessed,
    }
    with Session() as s:
        if all_headlines:
            headlines = s.query(*list(cols.values())).all()
        else:
            headlines = s.query(*list(cols.values())).filter(Headline.processed == None).all()
    return pd.DataFrame(headlines, columns=[*cols.keys()])


if __name__ == '__main__':
    reprocess_headlines(True)