"""Explicit, bounded access before billing launches; never invent a paid plan."""
import os


def early_access_enabled():
    return (os.environ.get('INTEGRATION_EARLY_ACCESS_ENABLED') == '1'
            and os.environ.get('BUSINESS_BILLING_ENABLED') == '0')


def early_access_limit():
    try:
        return max(1, min(1000, int(os.environ.get('EARLY_ACCESS_MONTHLY_ASSESSMENT_LIMIT', '100'))))
    except (ValueError, TypeError):
        return 100


def integration_access(org):
    plan = getattr(org, 'plan', None) or 'trial'
    early = org is not None and early_access_enabled()
    return {
        'api': org is not None and (early or plan in ('integration', 'enterprise')),
        'widget': org is not None and (early or plan in ('team', 'integration', 'enterprise')),
        'earlyAccess': early,
        'earlyAccessMonthlyLimit': early_access_limit() if early and plan not in ('integration', 'enterprise') else None,
    }


def open_role_limit(org):
    """Workspace role allowance; approval and seat authorization remain separate gates."""
    if (getattr(org, 'plan', None) or 'trial') != 'trial':
        return None
    return 5 if org is not None and early_access_enabled() else 1
