"""One-time import of the data folder's JSON files into data.db (Nov 1, 2026), run by the alembic migration that
creates the tables. Each group's module has run(session, data, cache) -> dict of counts: it reads its files from the
data folder `data`, inserts their rows through `session` (a SQLAlchemy Session bound to the migration's connection),
and moves its caches into `cache`. It never deletes a source file: the files are removed by hand once the new code
has run on the database."""
GROUPS = ['runstate', 'records', 'showclaims', 'stories', 'narratives', 'motifs', 'caches']


def run_all(session, data: str, cache: str) -> dict:
    import importlib
    return {g: importlib.import_module(f'scripts.json_import.{g}').run(session, data, cache) for g in GROUPS}
