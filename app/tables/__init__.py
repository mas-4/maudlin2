"""Tables that replaced the JSON files in the data folder (Nov 1, 2026), one module per group. Each defines its
models on app.models.Base; app.models imports this package so alembic and create_all see them."""
from app.tables import runstate  # noqa: F401
from app.tables import records  # noqa: F401
from app.tables import showclaims  # noqa: F401
from app.tables import stories  # noqa: F401
from app.tables import narratives  # noqa: F401
from app.tables import motifs  # noqa: F401
from app.tables import caches  # noqa: F401
