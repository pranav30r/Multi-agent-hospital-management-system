from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    Return current UTC datetime as a naive datetime object.
    Maintains 100% compatibility with SQLite, PostgreSQL, and existing SQLAlchemy DateTime columns.
    Eliminates Python 3.12+ datetime.utcnow() deprecation warnings.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_iso() -> str:
    """Return current UTC ISO 8601 formatted string."""
    return datetime.now(timezone.utc).isoformat()
