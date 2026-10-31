"""Immutable Home Hosting retention; pure synthetic manifests, no provider I/O."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('home_hosting_assets',Path(__file__).parents[1]/'home_hosting_assets.py')
assets=importlib.util.module_from_spec(spec);spec.loader.exec_module(assets)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def files(*paths):
    return {path:digest(path)for path in paths}


def test_immutable_cache_headers_target_only_known_hashed_bundles():
    manifest=files('/index.html','/assets/index-New2026x.js','/assets/index-New2026x.css',
        '/assets/manual.js','/assets/index-New2026x.js.map','/__/firebase/init.js')
    assert set(assets.immutable_bundle_paths(manifest))=={
        '/assets/index-New2026x.js','/assets/index-New2026x.css'}
    assert '/assets/SuggestedTimes-Missing1.js' not in assets.immutable_bundle_paths(manifest)


def test_old_open_request_can_still_import_suggested_times_and_its_shared_css():
    current={'/index.html':digest('new entry'),**files('/assets/index-New2026x.js')}
    previous={'/index.html':digest('old entry'),**files(
        '/assets/index-Old2026x.js','/assets/SuggestedTimes-Dr6zvn8t.js',
        '/assets/SuggestedTimes-Sched123.css','/assets/common-Shared12.js')}
    combined=assets.merge_release_assets(current,[previous])
    assert combined['/index.html']==current['/index.html']
    assert combined['/assets/SuggestedTimes-Dr6zvn8t.js']==previous['/assets/SuggestedTimes-Dr6zvn8t.js']
    assert set(combined)==set(current)|{path for path in previous if path.startswith('/assets/')}


def test_all_team_payout_and_nested_lazy_dependencies_are_retained_as_a_release_graph():
    previous=files('/assets/Team-Team1234.js','/assets/OperatingRulesDraft-Rules123.js',
        '/assets/Payout-Payout12.js','/assets/ReceiptViewer-Receipt1.js',
        '/assets/common-Shared12.js','/assets/Team-Styling1.css')
    assert assets.merge_release_assets({},[previous])==previous
    with pytest.raises(ValueError,match='retained-file limit'):
        assets.merge_release_assets({},[previous],max_retained_files=len(previous)-1)


def test_only_hashed_public_js_css_are_copied_from_older_builds():
    excluded=files('/index.html','/privacy.html','/assets/index.js','/assets/style.css',
        '/assets/index-Old2026x.js.map','/assets/photo-Old2026x.png','/assets/private-Old2026x.json',
        '/assets/.env','/assets/.private-Old2026x.js','/private/secret-Old2026x.js',
        '/assets/subfolder/private-Old2026x.js','/assets/short-ab12.js')
    allowed=files('/assets/Team-Team1234.js','/assets/index-Styling1.css')
    assert assets.merge_release_assets({},[{**excluded,**allowed}])==allowed


def test_current_index_and_current_unhashed_files_are_authoritative_and_inputs_unchanged():
    current={'/index.html':digest('new page'),'/favicon.ico':digest('orange icon'),
        '/assets/current.js':digest('current unhashed file')}
    previous=[{'/index.html':digest('obsolete page'),'/favicon.ico':digest('old icon'),
        '/assets/current.js':digest('old unhashed'),**files('/assets/Team-Team1234.js')}]
    snapshot=copy.deepcopy((current,previous))
    result=assets.merge_release_assets(current,previous)
    assert all(result[path]==value for path,value in current.items())
    assert (current,previous)==snapshot
    result['/index.html']=digest('caller mutation')
    assert (current,previous)==snapshot


def test_originals_only_policy_expires_historical_bundles_instead_of_carrying_merged_maps():
    oldest=files('/assets/Ancient-Ancient1.js')
    previous=files('/assets/Previous-Prev1234.js')
    current=files('/assets/Current-Curr1234.js')
    previous_merged=assets.merge_release_assets(previous,[oldest])
    assert '/assets/Ancient-Ancient1.js'in previous_merged
    selected=assets.merge_release_assets(current,[previous,oldest],max_releases=1)
    assert selected=={**current,**previous}
    # A content map cannot reveal provenance. This demonstrates why the caller
    # must persist originals, never previous_merged, in the release cache.
    transitive=assets.merge_release_assets(current,[previous_merged],max_releases=1)
    assert '/assets/Ancient-Ancient1.js'in transitive


def test_newest_first_release_limit_and_zero_retention_are_explicit():
    current=files('/assets/current-Current1.js')
    newest=files('/assets/newest-Newest12.js')
    older=files('/assets/older-Older123.js')
    assert assets.merge_release_assets(current,[newest,older],max_releases=1)=={**current,**newest}
    assert assets.merge_release_assets(current,[newest],max_releases=0,max_retained_files=0)==current


def test_same_bundle_deduplicates_without_consuming_the_additional_file_budget():
    bundle=files('/assets/common-Shared12.js')
    assert assets.merge_release_assets(bundle,[bundle,bundle],max_retained_files=0)==bundle
    uppercase={path:value.upper()for path,value in bundle.items()}
    assert assets.merge_release_assets(uppercase,[bundle])==uppercase


@pytest.mark.parametrize('current,previous',[
    (files('/assets/common-Shared12.js'),{'/assets/common-Shared12.js':digest('changed')}),
    ({},{'/assets/common-Shared12.js':digest('first')}),
])
def test_immutable_path_collision_fails_between_current_or_previous_releases(current,previous):
    releases=[previous]
    if not current:releases.append({'/assets/common-Shared12.js':digest('second')})
    with pytest.raises(ValueError,match='different content'):
        assets.merge_release_assets(current,releases)


@pytest.mark.parametrize('bad',['','a'*63,'a'*65,'z'*64,123,None])
def test_invalid_digest_is_rejected_in_current_or_previous_maps(bad):
    with pytest.raises(ValueError,match='SHA-256'):
        assets.merge_release_assets({'/index.html':bad},[])
    with pytest.raises(ValueError,match='SHA-256'):
        assets.merge_release_assets({},[{'/assets/Team-Team1234.js':bad}])


@pytest.mark.parametrize('path',['assets/Team-Team1234.js','//assets/Team-Team1234.js',
    '/assets/../private-Team1234.js','/assets/%2e%2e/Team-Team1234.js',
    '/assets/Team-Team1234.js?token=x','/assets/Team-Team1234.js#fragment',
    '/assets\\Team-Team1234.js','/assets//Team-Team1234.js','/assets/Team-Team1234.js\n',None])
def test_unsafe_noncanonical_paths_fail_closed(path):
    with pytest.raises(ValueError,match='canonical'):
        assets.merge_release_assets({},[{path:digest('untrusted')}])


@pytest.mark.parametrize('kwargs',[{'max_releases':-1},{'max_releases':True},{'max_releases':1.5},
    {'max_retained_files':-1},{'max_retained_files':True},{'max_retained_files':None}])
def test_invalid_limits_fail_closed(kwargs):
    with pytest.raises(ValueError,match='limits'):
        assets.merge_release_assets({},[],**kwargs)


@pytest.mark.parametrize('current,previous',[(None,[]),([],[]),({},'history'),({},{}),({},[None])])
def test_invalid_manifest_shapes_are_rejected(current,previous):
    with pytest.raises(ValueError):assets.merge_release_assets(current,previous)
