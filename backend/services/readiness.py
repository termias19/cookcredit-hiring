"""Readiness checks for real database and shared rate-limit dependencies."""
import os


def readiness(database_check, storage):
    try:
        database_ok = bool(database_check())
    except Exception:
        database_ok = False
    shared_required = os.environ.get('COOKCREDIT_EXPECT_MULTI_INSTANCE') == '1'
    try:
        rate_limits_ok = bool(storage.check()) if shared_required else True
    except Exception:
        rate_limits_ok = False
    return {'database': database_ok, 'rateLimits': rate_limits_ok}, database_ok and rate_limits_ok
