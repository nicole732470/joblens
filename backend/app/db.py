import psycopg

from app.config import settings


def check_db_connection() -> bool:
    """Return True if the database is reachable. Used by /health."""
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
