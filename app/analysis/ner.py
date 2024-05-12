import multiprocessing as mp
import time
import uuid
from collections import namedtuple
from functools import partial
from typing import Optional

import pandas as pd
import requests
import spacy

from app.models import Session, NamedEntity, Headline, named_entity_association
from app.utils import get_logger

logger = get_logger(__name__)

labels = ['GPE', 'NORP', 'PERSON', 'ORG']

WikiData = namedtuple('Wikidata', ['id', 'canonical', 'description', 'patterns'])

run = str(uuid.uuid4().hex)


class EntityAnalyzer:
    def __init__(self):
        # we may need a better identifier
        self.nlp = spacy.load("en_core_web_lg")

    def extract_entities(self, text):
        return [(ent.text, ent.label_) for ent in filter(lambda x: x.label_ in labels, self.nlp(text).ents)]


def query_wikidata(entity_name) -> tuple[bool, Optional[WikiData]]:
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "language": "en",
        "format": "json",
        "search": entity_name.encode('utf-8')
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
    if res['success'] == 0 or not res['search']:
        return True, None
    bestmatch = res['search'][0]
    id_ = bestmatch['id']
    canonical = bestmatch['display']['label']['value']
    if 'description' not in bestmatch:
        bestmatch['description'] = ""
    description = bestmatch['description']
    if 'aliases' not in bestmatch:
        bestmatch['aliases'] = []
    patterns = bestmatch['aliases'] + [canonical]
    return True, WikiData(id_, canonical, description, patterns)


def reapply_entities(all_entities: bool = False):
    analyzer = EntityAnalyzer()
    df = query_data(all_entities)
    df = setup(df, analyzer)
    apply_entities(df)


def query_data(all_entities):
    logger.info("Querying data.")
    with Session() as s:
        if all_entities:
            # Delete all existing associations since we're clearly processing every headline
            s.query(named_entity_association).delete()
            query = s.query(Headline.id, Headline.processed).join(Headline.article)
        else:
            query = s.query(Headline.id, Headline.processed).join(Headline.article).filter(
                ~Headline.named_entities.any()
            )
        data = query.limit(100).all()
    df = pd.DataFrame(data, columns=['headline_id', 'title'])
    return df


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

    # Use 5 processes to extract entities
    num_processes = mp.cpu_count()
    num_headlines = len(df)
    # Calculate chunk size
    chunk_size = num_headlines // num_processes

    logger.info("Using %i processes to extract entities for %i headlines...", num_processes, num_headlines)

    fun = partial(process_chunk, analyzer.extract_entities)
    chunks = [df['title'][i:i + chunk_size] for i in range(0, len(df), chunk_size)]
    with mp.Pool(num_processes) as pool:
        result_chunks = pool.imap(fun, chunks)
        results = []
        for i, result_chunk in enumerate(result_chunks):
            results.extend(result_chunk)
            logger.info(f"Finished chunk {i + 1} of {len(chunks)}")

    df['raw_entities'] = results

    logger.info("Done.")

    df['entities'] = df['raw_entities'].apply(lambda x: [entity[0] for entity in x])
    df['labels'] = df['raw_entities'].apply(lambda x: [entity[1] for entity in x])
    # Flag for apply_entities
    df['run'] = run
    return df


def process_chunk(fun, texts):
    return [fun(text) for text in texts]


def apply_entities(df):
    """
    Requires a dataframe with a 'headline_id' column, a 'title' column,  and a 'raw_entities' column.
    To get the raw_entities, just use the setup function.
    """
    # Assert the dataframe has been run through setup by checking the run column
    if 'run' not in df.columns or df['run'].iloc[0] != run:
        raise ValueError("Dataframe must be run through setup first.")

    # Get a set of all unique entities
    unique_entities = list(set([entity for entities in df['raw_entities'] for entity in entities]))
    entity_df = get_entity_df(unique_entities)

    entity_df = get_all_wikidata(entity_df)

    map_and_update_headlines(df, entity_df)


def get_entity_df(unique_entities):
    logger.info("Getting existing ids")
    # Fill in the ids of existing entities
    entity_df = pd.DataFrame(unique_entities, columns=['entity', 'label'])
    # May also need to filter stuff like "A guy from..."
    entity_df['simplified'] = entity_df['entity'].apply(canonicalize)

    with Session() as s:
        entity_df['entity_id'] = entity_df.apply(
            lambda x: s.query(NamedEntity.id).filter(NamedEntity.patterns.like(f'%{x["simplified"].lower()}%')).first(),
            axis=1
        )
    # Upon retrieval these can be None or (id,) tuples so we need to flatten if they're not None
    entity_df['entity_id'] = entity_df['entity_id'].apply(lambda x: x[0] if x else None)

    entity_df['entity_id'] = entity_df['entity_id'].astype('Int64')
    entity_df['wikidata_id'] = None  # We don't need to query the wiki ids above because we won't be updating them
    entity_df['canonical'] = None  # same for all the rest
    entity_df['description'] = None
    entity_df['patterns'] = None
    entity_df['queried'] = False
    entity_df['committed'] = False
    return entity_df


def canonicalize(entity):
    # Remove 's and ' from the entity
    entity = entity.replace("'s", "")
    entity = entity.replace("'", "")
    return entity


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

    for i, row in entity_df[entity_df['entity_id'].isna()].iterrows():
        if row['queried']:
            continue

        while True:
            success, wikidata = query_wikidata(row['simplified'])
            if not success:
                logger.debug(f"Error querying Wikidata for {row['simplified']}")
                if sleep == 0:
                    sleep = 0.0001
                else:
                    sleep *= 2
            time.sleep(sleep)
            if success:
                break
        row['queried'] = True
        if not wikidata:
            continue

        # Check if any of the other unidentified match aliases
        aliases = [row['simplified']] + wikidata.patterns
        matches = entity_df[entity_df['simplified'].isin(aliases)]  # There will always be one match.
        # The patterns are now the union of all the patterns
        patterns = list(filter(None, set(wikidata.patterns + matches['patterns'].tolist())))

        entity_df.loc[matches.index, 'wikidata_id'] = wikidata.id
        entity_df.loc[matches.index, 'canonical'] = wikidata.canonical
        entity_df.loc[matches.index, 'description'] = wikidata.description
        entity_df.loc[matches.index, 'patterns'] = ','.join(patterns).lower()
        entity_df.loc[matches.index, 'queried'] = True

        if i % 50 == 0:  # TODO: Checkpoint to database
            logger.info(f"Checkpointing %i of %i: %s", i, unidentified_ids, row['simplified'])
            # Get rows that are queried but not committed and have a wiki_id
            updating_entities(queried_rows(entity_df))
            # Mark all queried rows as committed
            entity_df.loc[entity_df['queried'], 'committed'] = True

    updating_entities(queried_rows(entity_df))
    entity_df.loc[entity_df['queried'], 'committed'] = True
    entity_df = get_entity_ids(entity_df)
    logger.info("Ended querying with %i unidentified entities and a sleep of %f", unidentified_ids, sleep)
    return entity_df


def map_and_update_headlines(df, entity_df):
    # Drop entities for which we couldn't find a wikidata id
    entity_df.dropna(subset=['wikidata_id'], inplace=True)

    # Match the entities to the headlines by
    df['entity_ids'] = df['entities'].apply(
        lambda x: [entity_df[entity_df['entity'] == entity]['entity_id'].values[0] for entity in x]
    )
    # Make a df of all unique headline_ids and only headline_ids
    headline_ids = df['headline_id'].unique().tolist()

    # Now we can directly map headline_ids to entity_ids
    headline_entity_df = pd.DataFrame(
        [(headline_id, entity_id) for headline_id, entity_ids in
         df[['headline_id', 'entity_ids']].values for entity_id in entity_ids],
        columns=['headline_id', 'entity_id']
    )
    headline_entity_df.drop_duplicates(inplace=True)
    headline_entity_df.dropna(inplace=True)
    headline_entity_df.rename(columns={'entity_id': 'named_entity_id'}, inplace=True)

    with Session() as s:
        logger.info("Getting all current associations...")
        exists_df = pd.DataFrame(s.query(
            named_entity_association.c.headline_id, named_entity_association.c.named_entity_id
        ).all(), columns=['headline_id', 'named_entity_id'])

        logger.info("Dropping all existing associations from updates...")
        headline_entity_df = headline_entity_df[~headline_entity_df.isin(exists_df.to_dict(orient='records'))]

        logger.info("Inserting new associations...")
        s.execute(named_entity_association.insert().values(headline_entity_df.to_dict(orient='records')))

        logger.info("Updating all headlines so that ner_processed is True")
        s.query(Headline).filter(Headline.id.in_(headline_ids)).update({'ner_processed': True},
                                                                       synchronize_session=False)

        logger.info("Committing...")
        s.commit()
        logger.info("Done.")


def updating_entities(entity_df):
    # Now we need to insert the new entities into the database
    new_entities = entity_df[(entity_df['entity_id'].isna()) & (entity_df['wikidata_id'].notna())]
    new_entities = new_entities[['canonical', 'label', 'wikidata_id', 'description', 'patterns']]
    rows = new_entities.to_dict(orient='records')
    with Session() as s:
        s.bulk_insert_mappings(NamedEntity, rows)
        s.commit()


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
