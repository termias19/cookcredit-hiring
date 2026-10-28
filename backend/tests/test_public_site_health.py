import json
import socket
import pytest
import requests
from urllib3 import exceptions as transport_errors
from services.public_site_health import check_public_site, CANONICAL


class Response:
    status_code = 200
    def __init__(self, text, headers=None):
        self.text = text;self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size): yield self.text.encode()


def pages(*, environment='production'):
    return {
        '/': Response('<link rel="canonical" href="' + CANONICAL + '">',
                      {'X-Robots-Tag': 'noindex, nofollow'} if environment == 'staging' else {}),
        '/login': Response('Sign in', {'X-Robots-Tag': 'noindex, nofollow'}),
        '/robots.txt': Response('User-agent: *\nAllow: /\nSitemap: ' + CANONICAL + 'sitemap.xml'),
        '/sitemap.xml': Response('<urlset><url><loc>' + CANONICAL + '</loc></url></urlset>'),
    }


def getter(responses):
    def get(url, **options):
        assert options == {'timeout': (2, 4), 'allow_redirects': False, 'stream': True}
        return responses['/' + url.split('/', 3)[3]]
    return get


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_public_indexing_and_private_exclusions(environment, capsys):
    assert check_public_site(environment, get=getter(pages(environment=environment)))
    assert json.loads(capsys.readouterr().out)['severity'] == 'INFO'


@pytest.mark.parametrize('failure', ['home_noindex', 'private_index', 'wrong_canonical', 'wrong_sitemap', 'network'])
def test_regressions_are_logged_without_page_contents(failure, capsys):
    responses = pages()
    if failure == 'home_noindex': responses['/'].headers['X-Robots-Tag'] = 'noindex'
    if failure == 'private_index': responses['/login'].headers = {}
    if failure == 'wrong_canonical': responses['/'].text = '<link rel="canonical" href="https://other.example/">PRIVATE_TOKEN'
    if failure == 'wrong_sitemap': responses['/sitemap.xml'].text = '<urlset><url><loc>PRIVATE_TOKEN</loc></url></urlset>'
    get = getter(responses)
    if failure == 'network':
        def get(*args, **kwargs): raise RuntimeError('PRIVATE_TOKEN')
    assert not check_public_site('production', get=get)
    output = capsys.readouterr().out
    assert 'PRIVATE_TOKEN' not in output and json.loads(output)['severity'] == 'ERROR'


def test_local_development_never_calls_a_public_site():
    def forbidden(*args, **kwargs): raise AssertionError('No network')
    assert check_public_site('development', get=forbidden)


@pytest.mark.parametrize('error,category', [
    (requests.exceptions.ConnectTimeout('PRIVATE_TOKEN'), 'connect_timeout'),
    (requests.exceptions.ReadTimeout('PRIVATE_TOKEN'), 'read_timeout'),
    (requests.exceptions.SSLError('PRIVATE_TOKEN'), 'tls_error'),
    (requests.exceptions.ConnectionError(transport_errors.MaxRetryError(None, 'PRIVATE_TOKEN',
        transport_errors.NameResolutionError('PRIVATE_TOKEN', None, socket.gaierror('PRIVATE_TOKEN')))), 'dns_error'),
    (requests.exceptions.ConnectionError(transport_errors.NewConnectionError(None, 'PRIVATE_TOKEN')), 'connection_error'),
    (requests.exceptions.ConnectionError(transport_errors.ReadTimeoutError(None, 'PRIVATE_TOKEN', 'PRIVATE_TOKEN')), 'read_timeout'),
    (requests.exceptions.ChunkedEncodingError('PRIVATE_TOKEN'), 'incomplete_response'),
    (type('PRIVATE_TOKEN', (RuntimeError,), {})('PRIVATE_TOKEN'), 'unexpected_error'),
])
def test_safe_network_categories_keep_alerts_and_continue_other_checks(error, category, capsys):
    calls = []
    normal = getter(pages())
    def get(url, **options):
        calls.append(url)
        if url.endswith('/'):
            raise error
        return normal(url, **options)
    assert not check_public_site('production', get=get)
    output = capsys.readouterr().out
    assert 'PRIVATE_TOKEN' not in output and 'https://' not in output
    event = json.loads(output)
    assert event['severity'] == 'ERROR' and event['failures'] == ['home_unavailable']
    assert len(calls) == 4  # No new retry or early abort; Scheduler retains retries.
    detail = event['failureDetails'][0]
    assert set(detail) == {'probe', 'phase', 'category', 'elapsedMs'}
    assert detail['probe'] == 'home' and detail['phase'] == 'fetch'
    assert detail['category'] == category and detail['elapsedMs'] >= 0


@pytest.mark.parametrize('kind,phase,category', [
    ('read_timeout', 'read', 'read_timeout'),
    ('large', 'read', 'response_too_large'),
    ('utf8', 'decode', 'invalid_utf8'),
    ('xml', 'validate', 'invalid_xml'),
])
def test_response_failure_phase_and_status_without_response_contents(kind, phase, category, capsys):
    responses = pages()
    target = '/sitemap.xml' if kind == 'xml' else '/'
    response = responses[target]
    if kind == 'read_timeout':
        def read(**kwargs):
            raise requests.exceptions.ConnectionError(transport_errors.ReadTimeoutError(None, 'PRIVATE_TOKEN', 'PRIVATE_TOKEN'))
        response.iter_content = read
    elif kind == 'large':
        response.text = 'PRIVATE_TOKEN' * (128 * 1024)
    elif kind == 'utf8':
        response.iter_content = lambda **kwargs: iter([b'PRIVATE_TOKEN\xff'])
    else:
        response.text = '<urlset>PRIVATE_TOKEN'
    assert not check_public_site('production', get=getter(responses))
    output = capsys.readouterr().out
    assert 'PRIVATE_TOKEN' not in output
    detail = json.loads(output)['failureDetails'][0]
    assert detail['phase'] == phase and detail['category'] == category
    assert detail['statusCode'] == 200


def test_http_status_is_reported_without_headers_body_or_exception(capsys):
    responses = pages()
    responses['/'].status_code = 503
    responses['/'].text = 'PRIVATE_TOKEN'
    responses['/'].headers['Location'] = 'https://PRIVATE_TOKEN/'
    assert not check_public_site('production', get=getter(responses))
    output = capsys.readouterr().out
    event = json.loads(output)
    assert event['failures'] == ['home_http'] and event['severity'] == 'ERROR'
    assert event['failureDetails'][0]['statusCode'] == 503
    assert event['failureDetails'][0]['category'] == 'http_status'
    assert 'PRIVATE_TOKEN' not in output


def test_wrapped_exception_cycle_is_bounded_and_does_not_hide_alert(capsys):
    error = RuntimeError('PRIVATE_TOKEN')
    error.__cause__ = error
    def get(*args, **kwargs): raise error
    assert not check_public_site('production', get=get)
    output = capsys.readouterr().out
    assert 'PRIVATE_TOKEN' not in output
    assert json.loads(output)['severity'] == 'ERROR'


def test_probe_log_correlates_with_server_request_without_logging_caller_headers(capsys):
    from flask import Flask, g
    app = Flask(__name__)
    with app.test_request_context(headers={'X-Request-ID': 'PRIVATE_TOKEN'}):
        g.request_id = 'a' * 32
        assert check_public_site('production', get=getter(pages()))
    output = capsys.readouterr().out
    event = json.loads(output)
    assert event['requestId'] == 'a' * 32 and 'PRIVATE_TOKEN' not in output
    assert event['severity'] == 'INFO' and event['failureDetails'] == []


def test_invalid_internal_reference_cannot_leak_into_operational_log(capsys):
    from flask import Flask, g
    app = Flask(__name__)
    with app.test_request_context():
        g.request_id = 'PRIVATE_TOKEN'
        assert check_public_site('production', get=getter(pages()))
    output = capsys.readouterr().out
    assert 'requestId' not in json.loads(output) and 'PRIVATE_TOKEN' not in output
