"""Public Hosting checks on the existing maintenance tick, outside SQL transactions."""
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
import requests
from urllib3 import exceptions as transport_errors
from services.operations import emit_event

ORIGINS = {'production': 'https://hiring.cookcredit.com',
           'staging': 'https://cookcredit-hiring-staging.web.app'}
CANONICAL = 'https://hiring.cookcredit.com/'
MAX_BYTES = 128 * 1024


class _PageTooLarge(ValueError):
    pass


def _failure_category(error):
    # Streaming Requests errors can wrap a transport error in args or reason.
    # Inspect types only, with a strict bound; never serialize exception text.
    chain, pending, seen = [], [error], set()
    while pending and len(chain) < 10:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current)); chain.append(current)
        pending.extend([current.__cause__, current.__context__])
        pending.extend(value for value in current.args if isinstance(value, BaseException))
        if isinstance(current, transport_errors.MaxRetryError):
            pending.append(current.reason)
    categories = (
        ('dns_error', (socket.gaierror, transport_errors.NameResolutionError)),
        ('read_timeout', (requests.exceptions.ReadTimeout, transport_errors.ReadTimeoutError)),
        ('tls_error', (requests.exceptions.SSLError, transport_errors.SSLError, ssl.SSLError)),
        ('connect_timeout', (requests.exceptions.ConnectTimeout, transport_errors.ConnectTimeoutError)),
        ('timeout', (requests.exceptions.Timeout, TimeoutError)),
        ('connection_reset', (ConnectionResetError,)),
        ('incomplete_response', (requests.exceptions.ChunkedEncodingError,)),
        ('content_decoding_error', (requests.exceptions.ContentDecodingError,)),
        ('connection_error', (requests.exceptions.ConnectionError, transport_errors.ProtocolError,
                              transport_errors.NewConnectionError, ConnectionError)),
        ('response_too_large', (_PageTooLarge,)),
        ('invalid_utf8', (UnicodeDecodeError,)),
        ('invalid_xml', (ET.ParseError,)),
        ('request_error', (requests.exceptions.RequestException,)),
    )
    for category, types in categories:
        if any(isinstance(value, types) and not (
                category == 'connect_timeout' and isinstance(value, transport_errors.NewConnectionError)
        ) for value in chain):
            return category
    return 'unexpected_error'


def check_public_site(environment, *, get=None):
    if environment not in ORIGINS:
        return True  # No local-development calls to production.
    origin = ORIGINS[environment]
    failures = []
    details = []
    paths = {'home': '/', 'login': '/login', 'robots': '/robots.txt', 'sitemap': '/sitemap.xml'}
    get = get or requests.get
    for name, path in paths.items():
        started = time.monotonic()
        phase, status = 'fetch', None

        def failed(code, category):
            failures.append(code)
            detail = {'probe': name, 'phase': phase, 'category': category,
                      'elapsedMs': max(0, int((time.monotonic() - started) * 1000))}
            if status is not None:
                detail['statusCode'] = status
            details.append(detail)

        try:
            # Fixed destinations only; do not follow a misconfigured cross-site redirect.
            with get(origin + path, timeout=(2, 4), allow_redirects=False, stream=True) as response:
                if isinstance(response.status_code, int) and 100 <= response.status_code <= 599:
                    status = response.status_code
                if response.status_code != 200:
                    failed(name + '_http', 'http_status')
                    continue
                phase = 'read'
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise _PageTooLarge()
                phase = 'decode'
                text = raw.decode('utf-8')
                phase = 'validate'
                header = response.headers.get('X-Robots-Tag', '').lower()
                meta = re.findall(r'<meta\b[^>]*(?:robots|googlebot)[^>]*>', text, re.I)
                excluded = any(token in header for token in ('noindex', 'none')) or any(
                    re.search(r'\b(?:noindex|none)\b', value, re.I) for value in meta)
                if name == 'home':
                    if excluded != (environment == 'staging'):
                        failed('home_indexing', 'indexing_policy')
                    if not re.search(r'<link\b[^>]*rel=[\"\x27]canonical[\"\x27][^>]*href=[\"\x27]' + re.escape(CANONICAL) + r'[\"\x27]', text, re.I):
                        failed('home_canonical', 'canonical_policy')
                elif name == 'login' and not excluded:
                    failed('private_indexing', 'indexing_policy')
                elif name == 'robots' and 'Sitemap: ' + CANONICAL + 'sitemap.xml' not in text:
                    failed('robots_sitemap', 'robots_sitemap_policy')
                elif name == 'sitemap':
                    locations = [node.text for node in ET.fromstring(text).findall('{*}url/{*}loc')]
                    if locations != [CANONICAL]:
                        failed('sitemap_locations', 'sitemap_locations_policy')
        except Exception as error:
            # Never log response bodies, provider errors, URLs or query strings.
            failed(name + '_unavailable', _failure_category(error))
    emit_event('public_site_health', severity='ERROR' if failures else 'INFO',
               environment=environment, failures=failures, checked=len(paths), failureDetails=details)
    return not failures
