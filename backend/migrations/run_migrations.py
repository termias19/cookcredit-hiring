#!/usr/bin/env python3
"""Ordered, idempotent SQL migration runner.

Applies every pending NNN_*.sql in numeric order and records each in a
`schema_migrations` table, so it is safe to re-run and reproduces the schema on a
fresh database (the gap the audit flagged: alembic/versions is empty; this replaces
the by-hand `psql -f 001_initial.sql` step that only ever applied 001).

Connection comes from the SAME resolver the app uses (services.database._build_url),
so it works against local Postgres, the Cloud SQL Auth Proxy (DATABASE_URL), or a
Cloud Run Job with the Cloud SQL Unix socket (CLOUD_SQL_CONNECTION + DB_USER/DB_PASS).

  python migrations/run_migrations.py            # apply all pending
  python migrations/run_migrations.py --status   # list applied vs pending, apply nothing

The runner removes an optional outer BEGIN/COMMIT wrapper and commits each migration
together with its marker. A PostgreSQL advisory lock serializes migration processes.
--status does not create tables or take the migration lock.
"""
import glob
import os
import re
import sys

# Import the app's URL resolver (backend/ is this file's grandparent).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.database import _build_url  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402

MIG_DIR = os.path.dirname(os.path.abspath(__file__))
LOCK_NAME = "hashtextextended(current_database() || ':' || current_schema() || ':cookcredit:migrations', 0)"


def discover():
    """All migration files (NNN_*.sql), numeric order, excluding this runner."""
    files = sorted(glob.glob(os.path.join(MIG_DIR, "[0-9][0-9][0-9]_*.sql")))
    return [(os.path.basename(f), f) for f in files]


def transaction_body(sql):
    """Existing files may wrap their body; only the runner may commit a migration."""
    whitespace_comments = r'(?:\s|--[^\n]*(?:\n|$))*'
    body, starts = re.subn(r'\A(' + whitespace_comments + r')BEGIN\s*;', r'\1', sql, count=1, flags=re.I)
    body, ends = re.subn(r'COMMIT\s*;(' + whitespace_comments + r')\Z', r'\1', body, count=1, flags=re.I)
    if starts != ends or re.search(r'^\s*(?:BEGIN|COMMIT|ROLLBACK)\s*;', body, flags=re.I | re.M):
        raise ValueError('Migration must have at most one outer BEGIN/COMMIT wrapper')
    return body


def migration_table(conn):
    # A fallback schema in search_path must never supply another application's markers.
    schema = conn.exec_driver_sql('SELECT current_schema()').scalar_one()
    if not schema:
        raise RuntimeError('Migration target schema does not exist')
    return conn.dialect.identifier_preparer.quote_schema(schema) + '.schema_migrations'


def apply_migration(conn, name, sql):
    # DDL and marker roll back together, including migrations without IF NOT EXISTS.
    with conn.begin():
        table = migration_table(conn)
        conn.exec_driver_sql(transaction_body(sql))
        conn.execute(text(f'INSERT INTO {table}(filename) VALUES (:filename)'), {'filename': name})


def run(conn, *, status_only=False):
    if not status_only:
        conn.exec_driver_sql('SELECT pg_advisory_lock(' + LOCK_NAME + ')')
        conn.commit()
    try:
        table = migration_table(conn)
        if not status_only:
            conn.exec_driver_sql(
                f"CREATE TABLE IF NOT EXISTS {table} ("
                "  filename TEXT PRIMARY KEY,"
                "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        exists = conn.execute(text('SELECT to_regclass(:table)'), {'table': table}).scalar()
        applied = {r[0] for r in conn.exec_driver_sql(f'SELECT filename FROM {table}')} if exists else set()
        conn.commit()

        all_files = discover()
        pending = [(n, p) for (n, p) in all_files if n not in applied]

        print(f"migrations: {len(all_files)} total, {len(applied)} applied, {len(pending)} pending")
        for name, _ in all_files:
            print(f"  [{'x' if name in applied else ' '}] {name}")

        if status_only:
            return 0
        if not pending:
            print("up to date — nothing to apply.")
            return 0

        for name, path in pending:
            with open(path, "r", encoding="utf-8") as fh:
                sql = fh.read()
            print(f"applying {name} ...", flush=True)
            apply_migration(conn, name, sql)
            print(f"  ✓ {name}")
    finally:
        if not status_only:
            conn.rollback()
            conn.exec_driver_sql('SELECT pg_advisory_unlock(' + LOCK_NAME + ')')
            conn.commit()

    print("done.")
    return 0


def main():
    engine = create_engine(_build_url(), future=True)
    try:
        with engine.connect() as conn:
            return run(conn, status_only='--status' in sys.argv)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
