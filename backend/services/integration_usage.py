"""Transactional monthly usage accounting for assessment integrations."""
import os
from datetime import datetime, timezone

from models import OrgAssessmentUsage
from services.integration_access import early_access_enabled, early_access_limit


def _period_start(now=None):
    today = (now or datetime.now(timezone.utc)).date()
    return today.replace(day=1)


def plan_limit(plan: str) -> int:
    if early_access_enabled() and plan not in ('integration', 'enterprise'):
        return early_access_limit()
    name = 'ENTERPRISE_MONTHLY_ASSESSMENT_LIMIT' if plan == 'enterprise' else 'INTEGRATION_MONTHLY_ASSESSMENT_LIMIT'
    default = '100000' if plan == 'enterprise' else '1000'
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return int(default)


def consume_request(session, *, org, environment='live') -> dict:
    """Increment once inside the caller's transaction; the caller must idempotency-check first."""
    period = _period_start()
    row = (session.query(OrgAssessmentUsage).filter_by(
        org_id=org.id, period_start=period, environment=environment)
           .with_for_update().one_or_none())
    if row is None:
        row = OrgAssessmentUsage(org_id=org.id, period_start=period,
                                 environment=environment, request_count=0)
        session.add(row); session.flush()
    limit = plan_limit(org.plan or 'trial')
    if row.request_count >= limit:
        raise ValueError('Monthly assessment request allowance reached')
    row.request_count += 1
    return {'periodStart': period.isoformat(), 'environment': environment, 'used': row.request_count,
            'limit': limit, 'remaining': max(0, limit - row.request_count)}


def current_usage(session, *, org, environment='live') -> dict:
    period = _period_start()
    row = session.query(OrgAssessmentUsage).filter_by(
        org_id=org.id, period_start=period, environment=environment).one_or_none()
    used = row.request_count if row else 0
    limit = plan_limit(org.plan or 'trial')
    return {'periodStart': period.isoformat(), 'environment': environment, 'used': used,
            'limit': limit, 'remaining': max(0, limit - used)}
