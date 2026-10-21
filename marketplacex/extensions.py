from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def commit_keeping_loaded() -> None:
    """Commit without expiring loaded rows, for read paths that commit a log row and then render what they
    loaded (reloading each row afterwards costs a round trip apiece on a remote database)."""
    session = db.session()
    keep, session.expire_on_commit = session.expire_on_commit, False
    try:
        session.commit()
    finally:
        session.expire_on_commit = keep
