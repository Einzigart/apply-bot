"""Database and configuration dependencies for FastAPI."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator
from fastapi import Request

from .. import db


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite database connection from app state."""
    db_path: Path = request.app.state.db_path
    conn = db.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()
