import multiprocessing as mp
import time
from collections import namedtuple
from functools import partial
from typing import Optional
from bs4 import BeautifulSoup as Soup

import numpy as np
import pandas as pd
import requests
import spacy
import sqlalchemy as sa
import os
from tqdm import tqdm

from app.models import Session, NamedEntity, Headline, NamedEntityAssociation
from app.utils import get_logger

tqdm.pandas()

logger = get_logger(__name__)

labels = ['GPE', 'NORP', 'PERSON', 'ORG']

WikiData = namedtuple('Wikidata', ['id', 'canonical', 'description'])


class EntityAnalyzer:
    def __init__(self):
        # we may need a better identifier
        try:
            spacy.require_gpu()
            self.gpu = True
        except:  # noqa
            self.gpu = False
        self.nlp = spacy.load("en_core_web_lg")

    def extract_entities(self, text):
        return [(ent.text, ent.label_) for ent in self.nlp(text).ents]


def query_wikidata(entity_name) -> tuple[bool, Optional[WikiData]]:
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": entity_name.encode('utf-8'),
        "format": "json",
        "srlimit": 1,
        "srnamespace": 0,
        "srprop": "snippet|titlesnippet"
    }
    res = requests.get(url, params=params)
    if res.status_code != 200:
        return False, None
    res = res.json()
    if 'warnings' in res:
        logger.warning("Wikidata returned a warning for '%s': %s", entity_name, res['warnings'])
    if 'error' in res:
        logger.error(res['error'])
        return False, None
    if res['query']['searchinfo']['totalhits'] == 0:
        return True, None
    wikidata_id = res['query']['search'][0]['title']
    description = res['query']['search'][0]['snippet']
    canonical = res['query']['search'][0]['titlesnippet']
    if '<' in canonical:
        soup = Soup(canonical, 'html.parser')
        canonical = soup.get_text()
    return True, WikiData(wikidata_id, canonical, description)


def reapply_entities(limit: int = 5_000):
    analyzer = EntityAnalyzer()
    df = query_data(limit)
    df = setup(df, analyzer)
    apply_entities(df)


def query_data(limit):
    logger.info("Querying data.")
    all_entities = True
    with Session() as s:
        if all_entities:
            # Delete all existing associations since we're clearly processing every headline
            s.query(NamedEntityAssociation).delete()
            query = s.query(Headline.id, Headline.processed).join(Headline.article)
        else:
            query = s.query(Headline.id, Headline.processed).join(Headline.article).filter(
                ~Headline.named_entities.any()
            )
        if limit:
            query = query.limit(limit)
        data = query.all()
    df = pd.DataFrame(data, columns=['headline_id', 'title'])
    return df


def process_chunk(f, chunk):
    return [f(row) for row in chunk]


def preprocess(df: pd.DataFrame):
    df['split'] = df['title'].str.split()
    df['word_count'] = df['split'].map(len)
    df['count_upper'] = df['split'].map(lambda x: sum(1 for c in x if c.isupper()))
    df['percent_upper'] = df['count_upper'] / df['word_count']
    df['tolower'] = df['percent_upper'] > 0.5
    df.loc[df['tolower'], 'title'] = df['title'].str.lower()
    df.drop(columns=['split', 'word_count', 'count_upper', 'percent_upper', 'tolower'], inplace=True)


def setup(df: pd.DataFrame, analyzer: EntityAnalyzer) -> pd.DataFrame:
    """
    Requires a simple dataframe with a 'title' column. Use the processed data from the database.
    """

    # Validate that the dataframe has the correct columns
    if 'title' not in df.columns:
        raise ValueError("Dataframe must have a 'title' column.")
    if 'headline_id' not in df.columns:
        raise ValueError("Dataframe must have a 'headline_id' column.")
    # Assert that there are no nulls in title or headline_id
    if df['title'].isnull().any():
        raise ValueError("Dataframe must not have any nulls in the 'title' column.")
    if df['headline_id'].isnull().any():
        raise ValueError("Dataframe must not have any nulls in the 'headline_id' column.")

    preprocess(df)

    num_headlines = len(df)

    logger.info("Extracting entities for %i headlines...", num_headlines)

    if os.path.exists('entity_checkpoint.csv'):
        df = pd.read_csv('entity_checkpoint.csv')
        return df

    if analyzer.gpu:
        df['raw_entities'] = df['title'].progress_apply(analyzer.extract_entities)
    else:
        n_processes = mp.cpu_count()
        with mp.Pool(n_processes) as pool:
            partial_extract = partial(analyzer.extract_entities, chunks=20_000)
            results = pool.imap(partial_extract, df['title'].tolist())
        df['raw_entities'] = list(tqdm(results, total=num_headlines))

        # Save df to a csv

    logger.info("Done.")

    # Explode the raw_entities column
    df = df.explode('raw_entities')
    df[['entity', 'label']] = df['raw_entities'].apply(pd.Series)
    # Drop rows where the label is not in the labels
    df = df[df['label'].isin(labels)]

    df['entity_split'] = df['entity'].str.split()
    df['entity_word_count'] = df['entity_split'].map(len)
    df = df[df['entity_word_count'] < 4]  # Any entity with more than 3 words is probably a glitch
    df = df.reset_index()
    df = df.drop(columns=['entity_split', 'entity_word_count', 'raw_entities', 'index'])
    df['simplified'] = df['entity'].str.replace("'s", "")
    df['simplified'] = df['simplified'].str.replace("'", "")

    # Flag for apply_entities
    df['run'] = True
    df.to_csv('entity_checkpoint.csv', index=False)
    return df


def apply_entities(df):
    """
    Requires a dataframe with a 'headline_id' column, a 'title' column,  and a 'raw_entities' column.
    To get the raw_entities, just use the setup function.
    """
    # Assert the dataframe has been run through setup by checking the run column
    if 'run' not in df.columns or not df['run'].iloc[0]:
        raise ValueError("Dataframe must be run through setup first.")

    df.drop(columns=['run'], inplace=True)

    # Get a set of all unique entities
    entity_df = get_entity_df(df)

    entity_df = get_all_wikidata(entity_df)

    map_and_update_headlines(df, entity_df)


def get_entity_df(df):
    logger.info("Getting existing ids...")

    with Session() as s:
        querycols = {
            'entity_id': NamedEntity.id,
            'patterns': NamedEntity.patterns,
            'wikidata_id': NamedEntity.wikidata_id,
            'canonical': NamedEntity.canonical
        }
        q = s.query(*querycols.values())
        existing_entities = df.apply(
            lambda x: q.filter(NamedEntity.patterns.like(f'%{x["simplified"]}%')).first() or [None] * 4, axis=1)

    existing_entity_df = pd.DataFrame(existing_entities.tolist(), columns=list(querycols.keys()))
    entity_df = pd.concat([df, existing_entity_df], axis=1)

    logger.info("Found %s existing entities", entity_df['entity_id'].notna().sum())
    entity_df['queried'] = False
    entity_df['committed'] = False

    entity_df.convert_dtypes()
    # convert headline_id and entity_id to ints
    entity_df['headline_id'] = entity_df['headline_id'].astype('Int64')
    entity_df['entity_id'] = entity_df['entity_id'].astype('Int64')

    for col in querycols.keys():
        entity_df[col] = entity_df[col].replace({np.nan: None})

    return entity_df


def merge_new_existing(entity_df, new_existing):  # noqa
    # We have a set of entities we've found with patterns we didn't know existed. They've now been updated.
    # We need to overwrite the patterns in the entity_df with the new patterns from new_existing
    # But first we should identify any rows in entity_df that match patterns in new_existing
    # And mark then queried

    # TODO Implement a function that merges the patterns together
    pass


def get_all_wikidata(entity_df):
    # We can't really do this because it slams the server I think.
    # unidentified_entities['wikidata'] = unidentified_entities['entity'].apply(query_wikidata)
    # We're going to instead do it sequentially and use exponential backoff
    sleep = 0
    unidentified_ids = len(entity_df[entity_df['entity_id'].isna()])

    # Mark all non null entities as queried and committed
    entity_df.loc[entity_df['entity_id'].notna(), 'queried'] = True
    entity_df.loc[entity_df['entity_id'].notna(), 'committed'] = True

    def queried_rows(df):
        return df[(df['queried']) & (~df['committed']) & (df['wikidata_id'].notna())]

    last_error = 0
    query = 0
    for i, (idx, row) in enumerate(entity_df[entity_df['entity_id'].isna()].iterrows()):
        if row['queried']:
            continue

        while True:
            success, wikidata = query_wikidata(row['simplified'])
            query += 1
            if not success:
                last_error = query
                logger.debug("Error querying Wikidata for %s", row['simplified'])
                if sleep == 0:
                    sleep = 0.0001
                else:
                    sleep *= 2
                if sleep > 0 and query - last_error > 1000:
                    logger.debug("It's been %i queries since the last error. Speeding back up.")
                    sleep /= 2
            time.sleep(sleep)
            if success:
                break
        row['queried'] = True
        if not wikidata:
            continue

        patterns = [row['simplified']]
        # Check if the entity is already in the entity_df
        if entity_df[entity_df['wikidata_id'] == wikidata.id].shape[0] > 1:
            # Combine all the patterns
            existing_patterns = ','.join(entity_df[entity_df['wikidata_id'] == wikidata.id]['patterns'].tolist())
            patterns = ','.join(list(set(existing_patterns.split(',') + patterns)))
            entity_df.loc[entity_df['wikidata_id'] == wikidata.id, 'patterns'] = patterns
            continue

        # Check if any of the other unidentified match aliases
        matches = entity_df[entity_df['simplified'].isin(patterns)]  # There will always be one match.
        # The patterns are now the union of all the patterns
        patterns = ','.join(filter(None, patterns + matches['patterns'].tolist()))
        patterns = list(set(patterns.split(',')))

        entity_df.loc[matches.index, 'wikidata_id'] = wikidata.id
        entity_df.loc[matches.index, 'canonical'] = wikidata.canonical
        entity_df.loc[matches.index, 'description'] = wikidata.description
        entity_df.loc[matches.index, 'patterns'] = ','.join(patterns).lower()
        entity_df.loc[matches.index, 'queried'] = True

        queried = queried_rows(entity_df)
        if len(queried) > 50:
            # Get rows that are queried but not committed and have a wiki_id
            # I want to know how many left. Just check how many not queried
            unidentified_ids = len(entity_df[(entity_df['entity_id'].isna()) & (~entity_df['queried'])])
            logger.info(
                "Checkpointing %i entities on iter %i of %i: %s (idx %i) (sleep: %f)",
                len(queried),
                i,
                unidentified_ids,
                row['simplified'],
                idx,
                sleep
            )
            new_existing = updating_entities(queried)
            merge_new_existing(entity_df, new_existing)  # Does nothing

            # Mark all queried rows as committed
            entity_df.loc[entity_df['queried'], 'committed'] = True

    updating_entities(queried_rows(entity_df))
    entity_df.loc[entity_df['queried'], 'committed'] = True
    entity_df = get_entity_ids(entity_df)
    logger.info("Ended querying with %i unidentified entities and a sleep of %f", unidentified_ids, sleep)
    return entity_df


def map_and_update_headlines(df, entity_df):
    # Drop entities for which we couldn't find a wikidata id
    entity_df.dropna(subset=['entity_id'], inplace=True)

    def match_id(x):
        match = entity_df.loc[entity_df['entity'] == x, 'entity_id']
        if match.empty:
            return None
        return match.values[0]

    # Match the entities to the headlines by checking if the entity is in the headline
    # In the DF we have an 'entity' column with the entity, and the same in the entity_df
    # We need to get the entity_id from the entity_df and put it in the df
    # TODO: There has got to be a better way to do this than another apply
    # That said, this is far from the slowest part of the process
    df['entity_id'] = df['entity'].apply(match_id)
    headline_entity_df = df[['headline_id', 'entity_id', 'entity', 'label']].drop_duplicates().copy()
    headline_entity_df.dropna(inplace=True)
    headline_entity_df.rename(columns={'entity_id': 'named_entity_id'}, inplace=True)
    headline_ids = headline_entity_df['headline_id'].unique()

    with Session() as s:
        logger.info("Getting all current associations...")
        exists_df = pd.DataFrame(s.query(
            NamedEntityAssociation.headline_id, NamedEntityAssociation.named_entity_id
        ).all(), columns=['headline_id', 'named_entity_id'])

        logger.info("Dropping all existing associations from updates...")
        headline_entity_df = headline_entity_df[~headline_entity_df.isin(exists_df.to_dict(orient='records'))]

        logger.info("Inserting new associations...")
        s.execute(
            NamedEntityAssociation.__table__.insert().values(headline_entity_df.to_dict(orient='records')))  # noqa

        logger.info("Updating all headlines so that ner_processed is True")
        s.query(Headline).filter(Headline.id.in_(headline_ids)).update({'ner_processed': True},
                                                                       synchronize_session=False)

        logger.info("Committing...")
        s.commit()
        logger.info("Done.")


def updating_entities(entity_df):
    # Now we need to insert the new entities into the database
    new_entities = entity_df[(entity_df['entity_id'].isna()) & (entity_df['wikidata_id'].notna())]
    # Drop any duplicate wikidata_ids
    new_entities.drop_duplicates(subset='wikidata_id', inplace=True)
    new_entities = new_entities[['canonical', 'label', 'wikidata_id', 'description', 'patterns']]

    with Session() as s:
        existing_entities = pd.DataFrame(
            s.query(NamedEntity.id, NamedEntity.wikidata_id, NamedEntity.patterns).filter(
                NamedEntity.wikidata_id.in_(new_entities['wikidata_id'])
            ).all(),
            columns=['entity_id', 'wikidata_id', 'patterns']
        )

        # Get a list of wikidata_ids common to both
        common = set(existing_entities['wikidata_id']) & set(new_entities['wikidata_id'])
        new_existing = new_entities[new_entities['wikidata_id'].isin(common)]
        # Merge the patterns from the new existing df into the existing_entities df
        existing_entities = existing_entities.merge(new_existing[['wikidata_id', 'patterns']],
                                                    on='wikidata_id',
                                                    how='left')

        # Drop rows where patterns_x == patterns_y
        existing_entities = existing_entities[existing_entities['patterns_x'] != existing_entities['patterns_y']]
        # Combine the patterns. Sometimes the dumbest way is the best.
        existing_entities['patterns'] = existing_entities['patterns_x'] + ',' + existing_entities['patterns_y']
        existing_entities['patterns'] = existing_entities['patterns'].str.split(',')
        existing_entities['patterns'] = existing_entities['patterns'].apply(lambda x: ','.join(set(x)))

        # Update the patterns in the database
        existing_entities.drop(columns=['patterns_x', 'patterns_y'], inplace=True)
        existing_entities = existing_entities[['entity_id', 'patterns']]
        if not existing_entities.empty:
            updates = existing_entities.to_dict(orient='records')
            ne_table = NamedEntity.__table__
            stmt = ne_table.update().where(ne_table.c.id == sa.bindparam('entity_id')).values(  # noqa update() missing
                patterns=sa.bindparam('patterns'))
            s.execute(stmt, updates)

        # Drop the new_existing wikidata_ids from the new_entities df
        new_entities = new_entities[~new_entities['wikidata_id'].isin(common)]

        # Insert the new entities
        s.bulk_insert_mappings(NamedEntity, new_entities.to_dict(orient='records'))
        s.commit()
    return new_existing


def get_entity_ids(entity_df):
    with Session() as s:
        entity_ids = s.query(NamedEntity.id, NamedEntity.wikidata_id).filter(
            NamedEntity.wikidata_id.in_(entity_df['wikidata_id'])
        ).all()
    ids = pd.DataFrame(entity_ids, columns=['entity_id', 'wikidata_id'])

    entity_df = entity_df.merge(ids, on='wikidata_id', how='left')
    # keep the original entity_id if it exists, otherwise use the new one
    entity_df['entity_id'] = entity_df['entity_id_x'].combine_first(entity_df['entity_id_y'])
    entity_df['entity_id'] = entity_df['entity_id'].astype('Int64')
    return entity_df
