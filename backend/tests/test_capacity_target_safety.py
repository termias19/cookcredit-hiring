"""The load harness must reject production targets before touching a dependency."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('changes,optimize', [
    ({'DATABASE_URL': 'postgresql://cookcredit_test:dummy@production.invalid/cookcredit_test'}, False),
    ({'FIREBASE_STORAGE_BUCKET': 'cookcredit-hiring-media-915097816203'}, False),
    ({'CLOUD_SQL_CONNECTION': 'cookcredit-scoring:us-central1:cookcredit-hiring-db'}, False),
    ({}, True),
])
def test_integrated_load_refuses_unsafe_targets(changes, optimize):
    env = dict(os.environ)
    env.pop('CLOUD_SQL_CONNECTION', None)
    env.pop('PYTHONOPTIMIZE', None)
    env.update(DATABASE_URL='postgresql://cookcredit_test:dummy@127.0.0.1:5432/cookcredit_test',
        COOKCREDIT_EPHEMERAL_VERIFICATION='1', FIREBASE_STORAGE_BUCKET='cookcredit-hiring-load-915097816203')
    env.update(changes)
    result = subprocess.run([sys.executable, *(['-O'] if optimize else []),
        'scripts/verify_integrated_capacity.py'], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    expected = 'without Python optimization' if optimize else 'Only the disposable local database'
    assert expected in result.stderr
    assert 'Firebase Auth connected' not in result.stdout
