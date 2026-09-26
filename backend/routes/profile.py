"""
Profile image upload endpoint.

All portfolio images are validated server-side before storage:
  1. Content-Length checked before reading (fast reject)
  2. Magic bytes identify real file type (never trust Content-Type header)
  3. Pillow opens and force-decodes the image (catches corrupt/malicious bodies)
  4. Image re-encoded fresh through Pillow — strips ALL EXIF including GPS,
     device info, timestamps, and embedded thumbnails. Also destroys any
     steganographic content or data appended after the image EOF marker.
  5. Uploaded to Firebase Storage via Admin SDK (bypasses client-side rules)
  6. Download token set so URL format matches Firebase getDownloadURL() output
"""
import io
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Blueprint, jsonify, request, g
from PIL import Image, UnidentifiedImageError

from extensions import limiter
from middleware.auth import require_auth
from services.firebase import get_storage_bucket

profile_bp = Blueprint("profile", __name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_FILE_SIZE = 10 * 1024 * 1024   # 10 MB hard limit
MAX_IMAGE_PIXELS = 25_000_000      # 25 megapixels — blocks decompression bombs

# Allowed output MIME types and their Pillow format strings
ALLOWED_FORMATS = {
    'JPEG': 'image/jpeg',
    'PNG':  'image/png',
    'WEBP': 'image/webp',
}

# Pillow's decompression bomb guard — must set before any Image.open() call
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_format(header: bytes) -> str | None:
    """Return Pillow format name from magic bytes, or None if not allowed.

    Reads the first 12 bytes only. Never trusts Content-Type or file extension.
    """
    if header[:3] == b'\xff\xd8\xff':
        return 'JPEG'
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return 'PNG'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'WEBP'
    return None


def _strip_and_reencode(data: bytes, fmt: str) -> bytes:
    """Validate with Pillow and re-encode without EXIF.

    Steps:
      - img.verify() — structural integrity check (truncation, corruption)
      - Re-open (verify exhausts the stream object)
      - img.load()   — force full pixel decode (catches corrupt body after valid header)
      - img.save()   — re-encode fresh, omitting any EXIF/metadata
        • Pillow's save() does NOT copy EXIF by default when no exif= kwarg is passed
        • This also removes GPS, device fingerprint, timestamps, embedded thumbnails,
          and any data appended after the image EOF marker (e.g. zip-in-image tricks)

    Raises ValueError on any validation failure.
    """
    buf = io.BytesIO(data)

    # Step 1 — structural check
    try:
        img = Image.open(buf)
        img.verify()
    except Exception as exc:
        raise ValueError(f"Image failed integrity check: {exc}") from exc

    # Step 2 — full pixel decode (must re-open after verify())
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValueError(f"Image could not be fully decoded: {exc}") from exc

    # Step 3 — mode normalisation
    if fmt == 'JPEG':
        # JPEG does not support alpha; flatten RGBA/P to RGB
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
    elif fmt == 'PNG':
        # Keep RGBA for PNG, normalise anything else to RGBA
        if img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
            img = img.convert('RGBA')
    elif fmt == 'WEBP':
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA' if img.mode == 'PA' else 'RGB')

    # Step 4 — re-encode without metadata
    out = io.BytesIO()
    if fmt == 'JPEG':
        img.save(out, format='JPEG', quality=88, optimize=True)
    elif fmt == 'PNG':
        img.save(out, format='PNG', optimize=True)
    elif fmt == 'WEBP':
        img.save(out, format='WEBP', quality=85, method=4)

    return out.getvalue()


def _firebase_download_url(bucket, blob_name: str, token: str) -> str:
    """Build a Firebase Storage download URL matching getDownloadURL() format.

    This token-based URL works for any browser without requiring auth headers,
    which is correct for portfolio images meant to be publicly viewable.
    """
    encoded = quote(blob_name, safe='')
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}"
        f"/o/{encoded}?alt=media&token={token}"
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@profile_bp.route("/upload-portfolio", methods=["POST"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def upload_portfolio():
    """
    Accept a portfolio image, validate it server-side, strip EXIF, upload to
    Firebase Storage, and return the download URL.

    Expects: multipart/form-data with field 'file'
    Returns: { url: string }
    """

    # ── 1. Fast size reject from Content-Length header ────────────────────────
    # Saves bandwidth — client is told to stop uploading before we read bytes.
    # +8192 accounts for multipart boundary overhead.
    content_length = request.content_length
    if content_length is not None and content_length > MAX_FILE_SIZE + 8192:
        return jsonify({"error": "File too large. Maximum size is 10 MB."}), 413

    # ── 2. Extract file from multipart ────────────────────────────────────────
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided. Send as multipart/form-data field 'file'."}), 400

    # ── 3. Read with size cap (MAX_FILE_SIZE + 1 trick to detect overflow) ────
    data = file.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE:
        return jsonify({"error": "File too large. Maximum size is 10 MB."}), 413

    # ── 4. Detect real file type from magic bytes ─────────────────────────────
    img_format = _detect_format(data[:12])
    if img_format is None:
        return jsonify({
            "error": "File type not allowed. Upload JPEG, PNG, or WebP images only."
        }), 415

    # ── 5. Validate + strip EXIF via Pillow ───────────────────────────────────
    try:
        clean_data = _strip_and_reencode(data, img_format)
    except (UnidentifiedImageError, ValueError, OSError):
        return jsonify({"error": "Image could not be processed. The file may be corrupt."}), 415

    # ── 6. Upload to Firebase Storage via Admin SDK ───────────────────────────
    ext   = 'jpg' if img_format == 'JPEG' else img_format.lower()
    ts    = int(datetime.now(timezone.utc).timestamp() * 1000)
    path  = f"profiles/{g.user_id}/portfolio_{ts}.{ext}"
    mime  = ALLOWED_FORMATS[img_format]
    token = str(uuid.uuid4())

    try:
        bucket = get_storage_bucket()
        blob   = bucket.blob(path)

        # Upload the re-encoded bytes
        blob.upload_from_string(clean_data, content_type=mime)

        # Set Firebase download token so the URL works from any browser
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.patch()

        url = _firebase_download_url(bucket, path, token)
    except Exception:
        return jsonify({"error": "Storage upload failed. Please try again."}), 500

    return jsonify({"url": url}), 201
