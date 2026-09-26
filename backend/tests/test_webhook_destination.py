import socket
import ssl
from types import SimpleNamespace
import pytest
from services import partner_integrations as hooks


def address(ip):
    return (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fc00::1', '100.64.0.1'])
def test_private_destinations_fail_before_connecting(monkeypatch, ip):
    monkeypatch.setattr(hooks.socket, 'getaddrinfo', lambda *a, **k: [address('8.8.8.8'), address(ip)])
    with pytest.raises(RuntimeError):
        hooks._assert_public_destination('https://employer.example.test/webhook')


def test_transport_pins_checked_address_and_retains_certificate_validation(monkeypatch):
    resolutions, pools, sent, closed = [], [], [], []
    def resolve(*a, **kw):
        resolutions.append(a)
        return [address('8.8.8.8' if len(resolutions) == 1 else '127.0.0.1')]
    monkeypatch.setattr(hooks.socket, 'getaddrinfo', resolve)
    class Pool:
        def __init__(self, host, **kw): pools.append((host, kw))
        def urlopen(self, *a, **kw):
            sent.append((a, kw))
            return SimpleNamespace(status=204, close=lambda: closed.append('response'))
        def close(self): closed.append('pool')
    monkeypatch.setattr(hooks.urllib3, 'HTTPSConnectionPool', Pool)
    result = hooks._post_public_webhook('https://employer.example.test:8443/callback?version=1',
        data=b'{}', headers={'CookCredit-Signature': 'test'}, timeout=(3, 10), allow_redirects=False, stream=True)
    assert len(resolutions) == 1 and resolutions[0][1] == 8443
    assert pools[0][0] == '8.8.8.8'
    assert pools[0][1]['server_hostname'] == pools[0][1]['assert_hostname'] == 'employer.example.test'
    assert pools[0][1]['ssl_context'].verify_mode == ssl.CERT_REQUIRED
    assert sent[0][0] == ('POST', '/callback?version=1')
    assert sent[0][1]['headers']['Host'] == 'employer.example.test:8443'
    assert sent[0][1]['redirect'] is False and sent[0][1]['preload_content'] is False
    assert result.status_code == 204
    result.close()
    assert closed == ['response', 'pool']


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:password@example.com',
    'https://example.com:99999', 'https://example.com/path\nInjected:header',
    'https://example.com/'+'x'*1000, 'https://169.254.169.254/'])
def test_invalid_webhook_urls_are_rejected(url):
    with pytest.raises(ValueError): hooks.validate_webhook_url(url)
