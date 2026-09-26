from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from middleware import auth

@pytest.fixture(autouse=True)
def empty_cache():
    auth._cache.clear()
    yield
    auth._cache.clear()


def test_revocation_verified_before_cache_and_after_30_seconds(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, 'time', lambda: clock[0])
    provider = Mock()
    provider.verify_id_token.return_value = {'uid': 'user', 'exp': 4600}
    monkeypatch.setattr(auth, 'get_auth', lambda: provider)
    assert auth._verify_token('test-token')['uid'] == 'user'
    provider.verify_id_token.assert_called_once_with('test-token', check_revoked=True)
    provider.verify_id_token.side_effect = ValueError('revoked')
    clock[0] = 1029
    assert auth._verify_token('test-token')['uid'] == 'user'
    clock[0] = 1030
    with pytest.raises(ValueError): auth._verify_token('test-token')
    assert provider.verify_id_token.call_count == 2


@pytest.mark.parametrize('reason', ['disabled', 'revoked', 'provider unavailable'])
def test_failed_verification_never_enters_cache(monkeypatch, reason):
    provider = Mock()
    provider.verify_id_token.side_effect = ValueError(reason)
    monkeypatch.setattr(auth, 'get_auth', lambda: provider)
    for _ in range(2):
        with pytest.raises(ValueError): auth._verify_token('test-token')
    assert not auth._cache
    assert provider.verify_id_token.call_count == 2


def test_cache_cannot_extend_token_expiry(monkeypatch):
    clock=[1000.0]
    monkeypatch.setattr(auth.time,'time',lambda:clock[0])
    provider=Mock();provider.verify_id_token.return_value={'uid':'u','exp':1035}
    monkeypatch.setattr(auth,'get_auth',lambda:provider)
    auth._verify_token('test-token');clock[0]=1006
    provider.verify_id_token.side_effect=ValueError('expired')
    with pytest.raises(ValueError):auth._verify_token('test-token')
