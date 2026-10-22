"""Public Hosting checks on the existing maintenance tick, outside SQL transactions."""
import re
import xml.etree.ElementTree as ET
import requests
from services.operations import emit_event

ORIGINS = {'production': 'https://hiring.cookcredit.com',
           'staging': 'https://cookcredit-hiring-staging.web.app'}
CANONICAL = 'https://hiring.cookcredit.com/'
MAX_BYTES = 128 * 1024


def check_public_site(environment, *, get=None):
    if environment not in ORIGINS:
        return True  # No local-development calls to production.
    origin = ORIGINS[environment]
    failures = []
    paths = {'home': '/', 'login': '/login', 'robots': '/robots.txt', 'sitemap': '/sitemap.xml'}
    get = get or requests.get
    for name, path in paths.items():
        try:
            # Fixed destinations only; do not follow a misconfigured cross-site redirect.
            with get(origin + path, timeout=(2, 4), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    failures.append(name + '_http')
                    continue
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise ValueError('Oversized public page')
                text = raw.decode('utf-8')
                header = response.headers.get('X-Robots-Tag', '').lower()
                meta = re.findall(r'<meta\b[^>]*(?:robots|googlebot)[^>]*>', text, re.I)
                excluded = any(token in header for token in ('noindex', 'none')) or any(
                    re.search(r'\b(?:noindex|none)\b', value, re.I) for value in meta)
                if name == 'home':
                    if excluded != (environment == 'staging'):
                        failures.append('home_indexing')
                    if not re.search(r'<link\b[^>]*rel=[\"\x27]canonical[\"\x27][^>]*href=[\"\x27]' + re.escape(CANONICAL) + r'[\"\x27]', text, re.I):
                        failures.append('home_canonical')
                elif name == 'login' and not excluded:
                    failures.append('private_indexing')
                elif name == 'robots' and 'Sitemap: ' + CANONICAL + 'sitemap.xml' not in text:
                    failures.append('robots_sitemap')
                elif name == 'sitemap':
                    locations = [node.text for node in ET.fromstring(text).findall('{*}url/{*}loc')]
                    if locations != [CANONICAL]:
                        failures.append('sitemap_locations')
        except Exception:
            # Never log response bodies, provider errors, URLs or query strings.
            failures.append(name + '_unavailable')
    emit_event('public_site_health', severity='ERROR' if failures else 'INFO',
               environment=environment, failures=failures, checked=len(paths))
    return not failures
