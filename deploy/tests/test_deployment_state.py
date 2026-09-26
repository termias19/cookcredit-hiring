import importlib.util
from pathlib import Path
import pytest
from uuid import uuid4

spec = importlib.util.spec_from_file_location('hiring_staging_state_test', Path(__file__).parents[1]/'hiring_staging.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def ledger(monkeypatch):
    # The desktop sandbox cannot reopen pytest's mode-0700 temp directories.
    # Use a unique ordinary workspace directory without deleting existing paths.
    folder = Path(__file__).resolve().parents[3]/'work/deployment-ledger-tests'/uuid4().hex
    folder.mkdir(parents=True)
    monkeypatch.setattr(module, 'STATE_FILE', folder/'state.json')
    initial = module.state()
    initial['release'] = 'previous'
    module.save(initial)
    return module


def test_independent_long_running_deployments_do_not_erase_each_other(ledger):
    frontend, migration = ledger.state(), ledger.state()
    frontend['release'] = 'new-frontend'
    ledger.save(frontend)
    migration['migrationSucceeded'] = True
    ledger.save(migration)
    assert ledger.state()['release'] == 'new-frontend'
    assert ledger.state()['migrationSucceeded'] is True
    assert migration['release'] == 'new-frontend'


def test_conflicting_release_updates_fail_closed(ledger):
    first, second = ledger.state(), ledger.state()
    first['release'] = 'new-frontend'
    second['release'] = 'another-frontend'
    ledger.save(first)
    with pytest.raises(RuntimeError, match='Concurrent deployment'):
        ledger.save(second)
    assert ledger.state()['release'] == 'new-frontend'


def test_deleting_own_old_field_keeps_unrelated_new_fields(ledger):
    cleanup, migration = ledger.state(), ledger.state()
    migration['migrationSucceeded'] = True
    ledger.save(migration)
    cleanup.pop('release')
    ledger.save(cleanup)
    assert 'release' not in ledger.state()
    assert ledger.state()['migrationSucceeded'] is True
