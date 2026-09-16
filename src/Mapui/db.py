"""Explicit configuration; the local application never defaults to production."""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DSN = f"dbname=sensnetdb_local host={ROOT / '.local/pgsocket'} port=55432"


@contextmanager
def database(write=False):
    conn = psycopg2.connect(
        os.getenv("DAS_DATABASE_URL", DEFAULT_DSN), connect_timeout=5
    )
    try:
        conn.set_session(readonly=not write)
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = '10s'")
            yield cur
    finally:
        conn.close()


def rows(sql, params=()):
    with database() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())
