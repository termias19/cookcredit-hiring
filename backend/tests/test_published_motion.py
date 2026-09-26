"""Golden outputs execute the exact hash-pinned published JavaScript, not this port."""
import json
from pathlib import Path

import pytest

from services.published_motion import score_motion_samples

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/published_motion/golden.json').read_text(encoding='utf-8'))['fixtures']


@pytest.mark.parametrize('case', FIXTURES, ids=[row['name'] for row in FIXTURES])
def test_published_javascript_parity(case):
    actual = score_motion_samples(case['samples'])
    for key, expected in case['expected'].items():
        if expected is None:
            assert actual[key] is None, key
        else:
            assert actual[key] == pytest.approx(expected, abs=1e-8), key


@pytest.mark.parametrize('samples', [None, [None], [[True, 0, 0]], [[0, 0, float('nan')]],
                                    [[0, 0, 0], [0, 0, 1]], [[181, 0, 0]], [[0, 0, 16385]]],
                         ids=['not-sequence', 'invalid-row', 'boolean', 'nan', 'unordered', 'duration', 'coordinates'])
def test_rejects_invalid_samples(samples):
    with pytest.raises(ValueError):
        score_motion_samples(samples)


def test_bounds_sample_count():
    with pytest.raises(ValueError):
        score_motion_samples([[i / 100, 0, 0] for i in range(4001)])
