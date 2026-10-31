"""Exercise actual non-owner grants in an explicitly disposable local database."""
import os
import secrets

import pytest
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError


def test_migrated_runtime_can_start_but_cannot_rewrite_audit_or_schema(monkeypatch):
    raw = os.getenv('HOME_TEST_DATABASE_URL') or os.getenv('HIRING_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Explicit disposable localhost PostgreSQL required')
    source = make_url(raw)
    assert source.host in ('127.0.0.1', 'localhost')
    assert source.username == 'cookcredit_test' and source.database == 'cookcredit_test'
    admin = create_engine(source, isolation_level='AUTOCOMMIT')
    target = 'cookcredit_home_test'
    roles = ('cookcredit_home_migrator', 'cookcredit_home_app')
    created_roles, created_database, engines = [], False, []
    try:
        with admin.connect() as conn:
            if not conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='postgis')")).scalar():
                pytest.skip('The dedicated role test requires PostGIS, provided by CI')
            assert not conn.execute(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': target}).scalar(), 'Refusing an existing Home test database'
            assert not conn.execute(text('SELECT 1 FROM pg_roles WHERE rolname IN (:a,:b)'), {'a': roles[0], 'b': roles[1]}).first(), 'Refusing existing Home test roles'
            passwords = {role: secrets.token_urlsafe(32) for role in roles}
            cursor = conn.connection.driver_connection.cursor()
            for role in roles:
                cursor.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT').format(sql.Identifier(role), sql.Literal(passwords[role])))
                created_roles.append(role)
            cursor.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(target), sql.Identifier(roles[0])))
            created_database = True
            cursor.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(target)))
            cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(target), sql.Identifier(roles[1])))
            cursor.close()
        setup = create_engine(source.set(database=target)); engines.append(setup)
        with setup.begin() as conn:
            conn.exec_driver_sql('CREATE EXTENSION postgis')
            conn.exec_driver_sql('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        from home import migrate
        monkeypatch.setenv('COOKCREDIT_PRODUCT', 'home-services')
        monkeypatch.setenv('HOME_DATABASE_URL', source.set(database=target, username=roles[0], password=passwords[roles[0]]).render_as_string(hide_password=False))
        migrate.main()
        migrate.main()  # A second deployment must preserve the same schema/grants.
        runtime = create_engine(source.set(database=target, username=roles[1], password=passwords[roles[1]])); engines.append(runtime)
        from home_app import check_home_schema
        with runtime.connect() as conn:
            check_home_schema(conn)
            assert conn.execute(text('SELECT current_user')).scalar() == roles[1]
            assert conn.execute(text('SELECT count(*) FROM home_schema_migrations')).scalar() >= 4
            assert conn.execute(text("SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='home_events'")).scalar() == roles[0]
            for table in ('cook_availability','cook_blocked_dates'):
                for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
                    assert conn.execute(text('SELECT has_table_privilege(current_user,:table,:privilege)'),
                        {'table':table,'privilege':privilege}).scalar() is True
            assert conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='cook_availability'::regclass AND conname='home_availability_end_hour'")).scalar() is not None
        for statement in ('UPDATE home_events SET details=details', 'DELETE FROM home_commands',
                          'DELETE FROM home_quotes', 'INSERT INTO home_schema_migrations VALUES (\'unapproved.sql\')',
                          'CREATE TABLE unauthorized (id integer)'):
            with pytest.raises(ProgrammingError):
                with runtime.begin() as conn:
                    conn.exec_driver_sql(statement)
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            if created_database:
                conn.exec_driver_sql('DROP DATABASE cookcredit_home_test')
            for role in reversed(created_roles):
                cursor = conn.connection.driver_connection.cursor()
                cursor.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
                cursor.close()
        admin.dispose()
