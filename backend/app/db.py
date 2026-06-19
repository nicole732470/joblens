import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.config import settings


def check_db_connection() -> bool:
    """Return True if the database is reachable. Used by /health."""
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    """Run a read query and return rows as dicts."""
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        register_vector(conn)
        return conn.execute(query, params).fetchall()


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    rows = fetch_all(query, params)
    return rows[0] if rows else None
