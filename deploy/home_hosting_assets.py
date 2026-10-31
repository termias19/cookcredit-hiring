"""Pure selection of immutable Home bundles needed by already-open browser tabs.

The caller supplies complete ORIGINAL published-build path -> gzip SHA-256 maps,
newest first. Never feed a previously merged Hosting map back as an original:
doing so would carry transitive historical files beyond the retention window.
Provenance cannot be inferred from a content map, so the release orchestrator
must fetch/cache originals separately and persist the current original map.

Keeping old bundles available does not add initial-page downloads: index.html
and its imports remain exclusively those of the current build. An older open
tab downloads its own lazy modules only when the user opens that screen.
This module performs no file, cloud, database or network I/O.
"""
from collections.abc import Mapping,Sequence
import re

_DIGEST=re.compile(r'[a-fA-F0-9]{64}\Z')
_BUNDLE=re.compile(r'/assets/[A-Za-z0-9][A-Za-z0-9_.-]*-[A-Za-z0-9_-]{8,64}\.(?:js|css)\Z')


def _checked_files(files):
    if not isinstance(files,Mapping):
        raise ValueError('A release must be a path-to-digest mapping')
    result={}
    for path,digest in files.items():
        if (not isinstance(path,str)or not path.startswith('/')or path.startswith('//')
            or any(c in path for c in ('\\','%','?','#'))
            or any(ord(c)<=32 or ord(c)==127 for c in path)
            or any(part in ('','.','..')for part in path[1:].split('/'))):
            raise ValueError('Release paths must be canonical root-relative file paths')
        if not isinstance(digest,str)or not _DIGEST.fullmatch(digest):
            raise ValueError('Release digests must be hexadecimal SHA-256 values')
        result[path]=digest
    return result


def merge_release_assets(current,previous_builds,*,max_releases=8,max_retained_files=128):
    """Return current files plus selected previous builds' immutable JS/CSS.

    Select at most ``max_releases`` newest original releases. Retain every eligible
    hashed bundle from those releases, including nested lazy-screen dependencies;
    never truncate a selected release to fit ``max_retained_files``. That limit
    counts unique additional paths, excluding bundles already in ``current``.
    Older HTML, source maps, images, JSON, private/unhashed files and non-assets
    paths are excluded. Current entries (including index.html) remain unchanged.

    Invalid maps/limits or a different digest for an immutable retained pathname
    raise ValueError before any result is returned. Inputs are never mutated.
    ``max_releases=0`` deliberately retains no historical releases.
    """
    if (type(max_releases)is not int or max_releases<0
        or type(max_retained_files)is not int or max_retained_files<0):
        raise ValueError('Retention limits must be nonnegative integers')
    if not isinstance(previous_builds,Sequence)or isinstance(previous_builds,(str,bytes,bytearray)):
        raise ValueError('Previous builds must be a newest-first sequence of original maps')
    combined=_checked_files(current)
    retained=set()
    for original in previous_builds[:max_releases]:
        for path,digest in _checked_files(original).items():
            if not _BUNDLE.fullmatch(path):
                continue
            if path in combined:
                if combined[path].casefold()!=digest.casefold():
                    raise ValueError('Immutable bundle pathname has different content')
            else:
                combined[path]=digest
                retained.add(path)
    if len(retained)>max_retained_files:
        raise ValueError('Selected release bundles exceed the retained-file limit')
    return combined
