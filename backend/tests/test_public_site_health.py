import json
import pytest
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
