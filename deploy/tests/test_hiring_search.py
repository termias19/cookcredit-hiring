"""The public homepage is discoverable; account and evidence URLs stay excluded."""
import fnmatch
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'frontend'


def robots_header(path, rows):
    value = None
    for row in rows:
        if fnmatch.fnmatchcase(path, row['source']):
            for header in row['headers']:
                if header['key'].lower() == 'x-robots-tag':
                    value = header['value']
    return value


def test_only_public_home_is_indexable_in_production():
    rows = json.loads((FRONTEND / 'firebase.json').read_text())['hosting']['headers']
    for path in ['/', '/index.html']:
        assert robots_header(path, rows) == 'index, follow'
    for path in ['/login', '/signup', '/owner/access', '/business/candidates',
                 '/business/roles', '/apply/example', '/invite/example',
                 '/landing/assessment/index.html', '/account/action', '/missing']:
        assert robots_header(path, rows) == 'noindex, nofollow', path


def test_staging_blanket_exclusion_still_wins():
    rows = json.loads((FRONTEND / 'firebase.json').read_text())['hosting']['headers']
    # host_frontend appends this final rule; even its public root stays excluded.
    rows.append({'source': '**', 'headers': [{'key': 'X-Robots-Tag', 'value': 'noindex, nofollow'}]})
    assert robots_header('/', rows) == 'noindex, nofollow'
    assert robots_header('/index.html', rows) == 'noindex, nofollow'


def test_hiring_home_and_sitemap_use_the_hiring_host():
    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    assert '<link rel="canonical" href="https://hiring.cookcredit.com/"' in html
    assert '<meta property="og:url" content="https://hiring.cookcredit.com/"' in html
    urls = ET.parse(FRONTEND / 'public/sitemap.xml').findall('{*}url/{*}loc')
    assert [node.text for node in urls] == ['https://hiring.cookcredit.com/']
    assert 'Sitemap: https://hiring.cookcredit.com/sitemap.xml' in (FRONTEND / 'public/robots.txt').read_text()
