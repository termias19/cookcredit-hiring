"""Known maintenance interruptions can recover; unknown errors remain actionable."""
from types import SimpleNamespace
import json
import pytest
from sqlalchemy.exc import OperationalError, TimeoutError
from services.operations import dependency_diagnostic


@pytest.mark.parametrize('state', ['08000','08006','08003','57P01','57P02','57P03'])
def test_connection_interruptions_have_bounded_retryable_diagnostics(state):
    error=OperationalError('private SQL and address',{'token':'secret'},SimpleNamespace(pgcode=state))
    result=dependency_diagnostic(error)
    assert result=={'dependency':'database','reason':'connection_interrupted','sqlState':state,'retryableDependency':True}
    assert 'private' not in json.dumps(result) and 'secret' not in json.dumps(result)


@pytest.mark.parametrize('state', [None, '53300', '42501', '57014', 'PRIVATE_TOKEN', [], {}])
def test_unknown_permission_capacity_and_query_errors_are_not_silenced(state):
    result=dependency_diagnostic(OperationalError('private SQL',{},SimpleNamespace(pgcode=state)))
    assert result['retryableDependency'] is False
    assert result['reason']=='database_operational_error'
    assert 'private' not in json.dumps(result)


def test_pool_exhaustion_has_its_own_cause():
    assert dependency_diagnostic(TimeoutError('private'))=={
        'dependency':'database','reason':'pool_timeout','retryableDependency':True}


def test_invalidated_connection_does_not_require_a_sqlstate():
    error=OperationalError('private SQL',{},Exception('private'),connection_invalidated=True)
    assert dependency_diagnostic(error)['retryableDependency'] is True


@pytest.mark.parametrize('message,retryable', [
    ('connection to server at private-host failed: Connection refused',True),
    ('server closed the connection unexpectedly private@example.test',True),
    ('FATAL: password authentication failed for private@example.test',False),
    ('unclassified private@example.test',False),
])
def test_libpq_connection_start_errors_are_classified_without_leaking_text(message,retryable):
    from psycopg2 import OperationalError as DriverError
    result=dependency_diagnostic(OperationalError('private SQL',{},DriverError(message)))
    assert result['retryableDependency'] is retryable
    assert 'private' not in json.dumps(result)
