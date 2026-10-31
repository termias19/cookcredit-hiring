"""One-off Home DB bootstrap on the already-running Hiring staging instance.

Run only as an override of the existing staging administrator job. Passwords
arrive through Secret Manager references, never arguments or printed SQL. This
does not alter a Hiring database, restart an instance or rotate existing roles.
"""
import os

from psycopg2 import sql
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url

CONNECTION = 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-db'
DATABASE = 'cookcredit_home_staging'
MARKER = 'cookcredit-home:staging:v1'
ROLES = ('cookcredit_home_migrator', 'cookcredit_home_app')


def target(setting, role):
    value = make_url(os.environ[setting])
    if (value.drivername != 'postgresql+psycopg2' or value.database != DATABASE
            or value.username != role or not value.password or value.host
            or dict(value.query) != {'host': '/cloudsql/' + CONNECTION}):
        raise RuntimeError('Home bootstrap target rejected')
    return value


def main():
    if (os.getenv('HOME_STAGING_BOOTSTRAP') != '1' or os.getenv('COOKCREDIT_ENVIRONMENT') != 'staging'
            or os.getenv('CLOUD_SQL_CONNECTION') != CONNECTION
            or os.getenv('CLOUD_RUN_JOB') != 'cc-hiring-stg-migrate'):
        raise RuntimeError('Home bootstrap requires the existing staging admin job')
    migration = target('HOME_DATABASE_URL', ROLES[0])
    application = target('HOME_RUNTIME_DATABASE_URL', ROLES[1])
    admin_url = URL.create('postgresql+psycopg2', username='postgres', password=os.environ['DB_PASS'],
                          database='postgres', query={'host': '/cloudsql/' + CONNECTION})
    admin = create_engine(admin_url, isolation_level='AUTOCOMMIT', connect_args={'connect_timeout': 5,
        'options': '-c statement_timeout=30000 -c lock_timeout=3000'})
    try:
        with admin.connect() as connection:
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute("SELECT current_setting('max_connections')::int-count(*) FROM pg_stat_activity")
            if cursor.fetchone()[0] < 12:
                raise RuntimeError('Insufficient existing connection headroom')
            for role, url in zip(ROLES, (migration, application)):
                cursor.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls,shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s", (role,))
                existing = cursor.fetchone()
                if existing:
                    if tuple(existing[:5]) != (False,) * 5 or existing[5] != MARKER:
                        raise RuntimeError('Existing Home role ownership/permissions rejected')
                else:
                    cursor.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS').format(sql.Identifier(role), sql.Literal(url.password)))
                    cursor.execute(sql.SQL('COMMENT ON ROLE {} IS {}').format(sql.Identifier(role), sql.Literal(MARKER)))
                cursor.execute('SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)', (role,))
                if cursor.fetchone():
                    raise RuntimeError('Home roles must not inherit other roles')
            cursor.execute("SELECT pg_get_userbyid(datdba),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", (DATABASE,))
            existing = cursor.fetchone()
            if existing and existing != (ROLES[0], MARKER):
                raise RuntimeError('Existing Home database ownership rejected')
            if not existing:
                cursor.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(DATABASE), sql.Identifier(ROLES[0])))
            cursor.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(ROLES[0])))
            cursor.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(DATABASE), sql.Literal(MARKER)))
            cursor.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(DATABASE)))
            cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(DATABASE), sql.Identifier(ROLES[1])))
            cursor.execute('RESET ROLE')
            cursor.close()
    finally:
        admin.dispose()
    setup = create_engine(admin_url.set(database=DATABASE), connect_args={'connect_timeout': 5})
    try:
        with setup.begin() as connection:
            connection.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS postgis')
            connection.exec_driver_sql('SET ROLE cookcredit_home_migrator')
            connection.exec_driver_sql('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            connection.exec_driver_sql('RESET ROLE')
    finally:
        setup.dispose()
    print('Home staging database and non-inheriting roles prepared on existing capacity.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not let DBAPI exception parameters expose password-bearing SQL.
        print('Home staging bootstrap failed: ' + type(error).__name__, flush=True)
        raise SystemExit(1)
