"""Explicit historical grants; new notices never expand earlier consent."""
APPLICATION_CONSENT_VERSION = 'cookcredit-hiring-application-v3'
ALL_ATTEMPTS_CONSENT_VERSIONS = frozenset({
    'cookcredit-hiring-application-v2', APPLICATION_CONSENT_VERSION,
})
