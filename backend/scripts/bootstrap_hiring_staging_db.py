"""Migrate only the named new staging DB, then grant a non-owner runtime role."""
import os
import subprocess
import sys
from sqlalchemy import create_engine, text
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.database import _build_url

if (os.environ.get('COOKCREDIT_ENVIRONMENT') != 'staging'
        or os.environ.get('CLOUD_SQL_CONNECTION') != 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-db'
        or os.environ.get('DB_NAME') != 'cookcredit_hiring_staging'
        or os.environ.get('DB_USER') != 'postgres'):
    raise SystemExit('Refusing migration outside the dedicated hiring staging database')

subprocess.run([sys.executable, 'migrations/run_migrations.py'], check=True)
engine = create_engine(_build_url())
with engine.begin() as connection:
    connection.exec_driver_sql('REVOKE ALL ON DATABASE cookcredit_hiring_staging FROM PUBLIC')
    connection.exec_driver_sql('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
    # SQL literals/identifiers are quoted by psycopg2. Never log the statement.
    raw = connection.connection.driver_connection
    cursor = raw.cursor()
    cursor.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', ('hiring_runtime',))
    if not cursor.fetchone():
        cursor.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(
            sql.Identifier('hiring_runtime'), sql.Literal(os.environ['RUNTIME_DB_PASS'])))
    cursor.close()
    connection.exec_driver_sql('GRANT CONNECT ON DATABASE cookcredit_hiring_staging TO hiring_runtime')
    connection.exec_driver_sql('GRANT USAGE ON SCHEMA public TO hiring_runtime')
    connection.exec_driver_sql('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hiring_runtime')
    connection.exec_driver_sql('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hiring_runtime')
    connection.exec_driver_sql('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hiring_runtime')
    connection.exec_driver_sql('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO hiring_runtime')
    # Runtime cannot alter the migration ledger, even though it owns no tables.
    connection.exec_driver_sql('REVOKE INSERT, UPDATE, DELETE ON schema_migrations FROM hiring_runtime')
    count = connection.execute(text('SELECT count(*) FROM schema_migrations')).scalar_one()
print(f'Staging migration complete: {count} migrations; runtime role has data access and no DDL ownership.')
