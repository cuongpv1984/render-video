from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from .config import settings

@contextmanager
def transaction():
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL must be configured")
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '15s'")
            yield cur
