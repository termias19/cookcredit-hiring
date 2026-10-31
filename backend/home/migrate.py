"""Explicit Home migration entrypoint. Never imported by the Hiring runner.

Run from backend: python -m home.migrate. Provision PostGIS in the dedicated
database first. No database creation, cloud activation or external calls occur.
"""
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from models import User, EaterProfile, CookProfile, Booking
from models.account_email import AccountEmail
from home_app import database_url
from migrations.run_migrations import transaction_body


def main():
    url = database_url()
    if make_url(url).username != 'cookcredit_home_migrator':
        raise RuntimeError('Home migrations require the dedicated migration role')
    engine = create_engine(url, connect_args={'connect_timeout': 5,
        'options': '-c statement_timeout=30000 -c lock_timeout=3000'}, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':home:migrate', 0))"))
            if conn.execute(text('SELECT current_database()')).scalar() != make_url(url).database:
                raise RuntimeError('Unexpected Home database target')
            if not conn.execute(text("SELECT to_regtype('geography') IS NOT NULL")).scalar():
                raise RuntimeError('Provision PostGIS in the Home database before migrating')
            # Reuse the actual core models, not copies of a legacy schema dump.
            for table in (User.__table__, EaterProfile.__table__, CookProfile.__table__, Booking.__table__, AccountEmail.__table__):
                table.create(conn, checkfirst=True)
            conn.exec_driver_sql('CREATE TABLE IF NOT EXISTS home_schema_migrations (filename TEXT PRIMARY KEY)')
            for path in sorted((Path(__file__).parent / 'migrations').glob('[0-9][0-9][0-9]_*.sql')):
                if not conn.execute(text('SELECT 1 FROM home_schema_migrations WHERE filename=:name'), {'name':path.name}).scalar():
                    conn.exec_driver_sql(transaction_body(path.read_text(encoding='utf-8')))
                    conn.execute(text('INSERT INTO home_schema_migrations VALUES (:name)'), {'name':path.name})
            # Application identity cannot rewrite audit or idempotency history.
            conn.exec_driver_sql('GRANT USAGE ON SCHEMA public TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT, INSERT, UPDATE ON users, bookings, home_visits, home_helper_permissions TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT ON cook_profiles, home_runtime_guard, home_schema_migrations TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT, INSERT ON home_events, home_commands TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT, UPDATE ON home_pricing_head TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT, INSERT ON home_rate_cards, home_quotes, home_quote_helper_acceptances, home_quote_approvals, home_material_reconciliations TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT, INSERT, UPDATE ON home_payments, home_financial_operations, home_stripe_events TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT UPDATE (stripe_account_id,stripe_onboarded) ON cook_profiles TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT INSERT,UPDATE ON cook_profiles TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT,INSERT,UPDATE ON eater_profiles,home_households,home_callbacks,account_emails TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT DELETE ON home_households TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT,INSERT,UPDATE ON home_receipts TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT,INSERT ON home_notification_cursors,home_access_audit TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT UPDATE (status) ON home_notification_cursors TO cookcredit_home_app')
            conn.exec_driver_sql('GRANT SELECT,INSERT,UPDATE ON home_operating_rules TO cookcredit_home_app')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
