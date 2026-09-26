"""Local dev DB helper. NOT for production.

Usage (from backend/, with the venv python):
    venv/Scripts/python.exe dev_db.py check            # show tables + key columns
    venv/Scripts/python.exe dev_db.py migrate          # apply migrations/*.sql in order (idempotent ones are safe to re-run)
    venv/Scripts/python.exe dev_db.py approve you@x.com # flip a cook application to approved (no admin panel yet)

Reads DATABASE_URL from backend/.env. Intended only against a LOCAL database.
"""
import glob
import os
import sys

from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text  # noqa: E402

URL = os.environ.get("DATABASE_URL")


def _engine(autocommit=False):
    if not URL:
        raise SystemExit("DATABASE_URL not set in backend/.env")
    return create_engine(URL, isolation_level="AUTOCOMMIT") if autocommit else create_engine(URL)


def check():
    with _engine().connect() as c:
        tabs = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public' order by 1"))]
        print("tables (%d): %s" % (len(tabs), ", ".join(tabs) or "(none)"))
        ext = c.execute(text("select 1 from pg_extension where extname='postgis'")).fetchone()
        print("postgis extension:", "yes" if ext else "NO (run: CREATE EXTENSION postgis;)")
        if "cook_profiles" in tabs:
            cols = [r[0] for r in c.execute(text(
                "select column_name from information_schema.columns where table_name='cook_profiles'"))]
            for col in ("applied_at", "approved", "skill_tier", "skill_score"):
                print("  cook_profiles.%s: %s" % (col, "yes" if col in cols else "MISSING"))


def migrate():
    files = sorted(glob.glob("migrations/*.sql"))
    if not files:
        print("no migrations/*.sql found (run from backend/)")
        return
    with _engine(autocommit=True).connect() as c:
        for f in files:
            print("applying %-34s" % f, end=" ")
            try:
                c.exec_driver_sql(open(f, encoding="utf-8").read())
                print("OK")
            except Exception as ex:
                # CREATE TABLE in 001 will error if the schema already exists — that
                # is expected on an already-initialized DB; later idempotent files
                # still apply.
                print("skipped/err:", str(ex).splitlines()[0][:140])


def approve(email):
    with _engine(autocommit=True).connect() as c:
        row = c.execute(text("select id from users where email=:e"), {"e": email}).fetchone()
        if not row:
            print("no user with email", email)
            return
        n = c.execute(text("update cook_profiles set approved=true where user_id=:u"),
                      {"u": row[0]}).rowcount
        if n:
            print("approved cook application for", email,
                  "— the cook role is granted on their next /api/auth/me load.")
        else:
            print("no cook_profiles row for", email, "(have they submitted an application?)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "check":
        check()
    elif mode == "migrate":
        migrate()
    elif mode == "approve" and len(sys.argv) > 2:
        approve(sys.argv[2])
    else:
        print(__doc__)
