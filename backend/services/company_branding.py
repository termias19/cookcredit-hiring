"""Public company logos, isolated from private applicant media."""
from io import BytesIO
import hashlib
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from google.api_core.exceptions import PreconditionFailed
from services.firebase import get_storage_bucket

MAX_LOGO_BYTES = 2 * 1024 * 1024


def normalize_logo(data):
    if not data or len(data) > MAX_LOGO_BYTES:
        raise ValueError('Choose a PNG, JPG or WebP logo smaller than 2 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValueError('Choose a PNG, JPG or WebP image.')
                width, height = source.size
                if width * height > 8_000_000 or max(width, height) > 4096:
                    raise ValueError('Choose an image no larger than 4096 pixels and 8 megapixels.')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Choose a still image for your logo.')
                source.load()
                picture = ImageOps.exif_transpose(source).convert('RGBA')
                picture.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                # A fresh image strips EXIF, ICC profiles and arbitrary metadata.
                clean = Image.new('RGBA', picture.size)
                clean.paste(picture)
                output = BytesIO()
                clean.save(output, format='PNG')
                encoded = output.getvalue()
                if len(encoded) > MAX_LOGO_BYTES:
                    raise ValueError('Choose a smaller or simpler logo image.')
                return encoded
    except (UnidentifiedImageError, OSError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('This image could not be read. Choose a valid PNG, JPG or WebP.') from exc


def logo_path(org_id, digest):
    return f'company_branding/{org_id}/{digest}.png'


def store_logo(org_id, encoded):
    digest = hashlib.sha256(encoded).hexdigest()
    blob = get_storage_bucket().blob(logo_path(org_id, digest))
    # No public bucket ACL and no Firebase token on any assessment object.
    try:
        blob.upload_from_string(encoded, content_type='image/png', if_generation_match=0, timeout=20)
    except PreconditionFailed:
        pass  # Identical normalized logo already exists for this organization.
    return digest


def read_logo(org_id, digest):
    return get_storage_bucket().blob(logo_path(org_id, digest)).download_as_bytes(timeout=15)
