import pandas as pd
import spacy
import requests
from collections import namedtuple
import time
from app.utils import get_logger
from typing import Optional
import multiprocessing as mp

from app.models import Session, NamedEntity, Article, Headline, named_entity_association

logger = get_logger(__name__)

labels = ['GPE', 'NORP', 'PERSON', 'ORG']

WikiData = namedtuple('Wikidata', ['id', 'canonical', 'description', 'patterns'])


class EntityAnalyzer:
    def __init__(self):
        # we may need a better identifier
        self.nlp = spacy.load("en_core_web_lg")

    def extract_entities(self, text):
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            if ent.label_ in labels:
                entities.append((ent.text, ent.label_))
        return entities


def query_wikidata(entity_name) -> tuple[bool, Optional[WikiData]]:
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "language": "en",
        "format": "json",
        "search": entity_name
    }
    res = requests.get(url, params=params)
    if res.status_code != 200:
        return False, None
    res = res.json()
    if 'warnings' in res:
        logger.warning(res['warnings'])
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
    df = setup(all_entities, analyzer)
    apply_entities(df)


def apply_entities(df):
    # Get a set of all unique entities
    unique_entities = list(set([entity for entities in df['raw_entities'] for entity in entities]))
    entity_df = get_entity_df(unique_entities)
    unidentified_entities = entity_df[entity_df['entity_id'].isna()]

    get_all_wikidata(entity_df, unidentified_entities)

    entity_df = updating_entities(entity_df)

    mapping_and_updating_articles(df, entity_df)


def mapping_and_updating_articles(df, entity_df):
    # Match the entities to the headlines by
    df['entity_ids'] = df['entities'].apply(
        lambda x: [entity_df[entity_df['entity'] == entity]['entity_id'].values[0] for entity in x]
    )
    # Now we can directly map article_ids to entity_ids
    article_entity_df = pd.DataFrame(
        [(article_id, entity_id) for article_id, entity_ids in
         df[['article_id', 'entity_ids']].values for entity_id in entity_ids],
        columns=['article_id', 'entity_id']
    )
    article_entity_df.drop_duplicates(inplace=True)
    article_entity_df.dropna(inplace=True)
    article_entity_df.rename(columns={'entity_id': 'named_entity_id'}, inplace=True)
    with Session() as s:
        s.execute(named_entity_association.insert().values(article_entity_df.to_dict(orient='records')))
        s.commit()


def updating_entities(entity_df):
    entity_df['patterns'] = entity_df['patterns'].str.lower()
    # Now we need to insert the new entities into the database
    new_entities = entity_df[(entity_df['entity_id'].isna()) & (entity_df['wikidata_id'].notna())]
    new_entities = new_entities[['canonical', 'label', 'wikidata_id', 'description', 'patterns']]
    rows = new_entities.to_dict(orient='records')
    with Session() as s:
        s.bulk_insert_mappings(NamedEntity, rows)
        s.commit()
        entity_ids = s.query(NamedEntity.id, NamedEntity.wikidata_id).filter(NamedEntity.wikidata_id.in_(new_entities['wikidata_id'])).all()
    ids = pd.DataFrame(entity_ids, columns=['entity_id', 'wikidata_id'])
    new_entities = new_entities.merge(ids, on='wikidata_id', how='left')
    new_entities['entity_id'] = new_entities['entity_id'].astype('Int64')
    entity_df = entity_df.merge(new_entities[['entity_id', 'wikidata_id']], on='wikidata_id', how='left')
    # keep the original entity_id if it exists, otherwise use the new one
    entity_df['entity_id'] = entity_df['entity_id_x'].combine_first(entity_df['entity_id_y'])
    return entity_df


def get_all_wikidata(entity_df, unidentified_entities):
    # We can't really do this because it slams the server I think.
    # unidentified_entities['wikidata'] = unidentified_entities['entity'].apply(query_wikidata)
    # We're going to instead do it sequentially and use exponential backoff
    sleep = 0
    for i, row in unidentified_entities.iterrows():
        if i % 100 == 0:
            logger.info(f"Querying {i} of {len(unidentified_entities)}: {row['simplified']}")
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
        entity_df.loc[matches.index, 'patterns'] = ','.join(patterns)
        entity_df.loc[matches.index, 'queried'] = True
        # I'm not sure if we still need these rows, but it might help with speed later to have them available
        # in entity columns instead of just in the patterns.


def canonicalize(entity):
    # Remove 's and ' from the entity
    entity = entity.replace("'s", "")
    entity = entity.replace("'", "")
    return entity


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
    return entity_df


def setup(all_entities, analyzer) -> pd.DataFrame:
    logger.info("Querying data.")
    with Session() as s:
        if all_entities:
            query = s.query(Article.id, Headline.id, Headline.processed).join(Headline.article)
        else:
            query = s.query(Article.id, Headline.id, Headline.processed).join(Headline.article).filter(
                ~Article.named_entities.any()
            )
        data = query.limit(1000).all()
    df = pd.DataFrame(data, columns=['article_id', 'headline_id', 'text'])

    # Use 5 processes to extract entities
    logger.info("Extracting entities...")
    with mp.Pool(16) as pool:
        df['raw_entities'] = pool.map(analyzer.extract_entities, df['text'])

    logger.info("Done.")

    df['entities'] = df['raw_entities'].apply(lambda x: [entity[0] for entity in x])
    df['labels'] = df['raw_entities'].apply(lambda x: [entity[1] for entity in x])
    # convert to a pandas dataframe
    return df
