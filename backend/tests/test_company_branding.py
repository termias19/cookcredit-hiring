from io import BytesIO
import pytest
from PIL import Image, PngImagePlugin
from services.company_branding import normalize_logo, MAX_LOGO_BYTES


def image_bytes(size=(40, 20), mode='RGBA', fmt='PNG', **kwargs):
    out = BytesIO()
    Image.new(mode, size).save(out, format=fmt, **kwargs)
    return out.getvalue()


def test_logo_preserves_aspect_and_transparency_but_removes_metadata():
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('private', 'should be removed')
    encoded = normalize_logo(image_bytes((2048, 1024), pnginfo=metadata))
    with Image.open(BytesIO(encoded)) as logo:
        assert logo.size == (1024, 512)
        assert logo.mode == 'RGBA'
        assert not logo.info


@pytest.mark.parametrize('data', [b'<svg><script>bad()</script></svg>', b'not an image', b'', b'x' * (MAX_LOGO_BYTES + 1)], ids=['svg', 'invalid', 'empty', 'oversized'])
def test_logo_rejects_invalid_and_oversized_uploads(data):
    with pytest.raises(ValueError):
        normalize_logo(data)


def test_logo_rejects_excessive_dimensions():
    with pytest.raises(ValueError, match='4096'):
        normalize_logo(image_bytes((4097, 1)))


def test_jpeg_is_reencoded_as_png():
    encoded = normalize_logo(image_bytes(mode='RGB', fmt='JPEG'))
    assert encoded.startswith(b'\x89PNG\r\n\x1a\n')
