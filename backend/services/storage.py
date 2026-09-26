"""Storage helpers (Firebase Storage / GCS).

Two patterns:
  * signed_upload_url(): mint a short-lived v4 signed PUT URL so the BROWSER
    uploads large files (skill videos, portfolio images) DIRECTLY to the bucket
    -- keeping big uploads off the API request workers (the scalability win).
  * firebase_download_url(): build the token-based public download URL
    (matches the format the web getDownloadURL() produces). Centralized here so
    routes stop copy-pasting it.

Requires the service account to be able to sign (the firebase-admin credentials
JSON carries the private key; on Cloud Run grant iam.serviceAccounts.signBlob).

INFRA PREREQ for direct upload to work from the browser: the bucket must allow
CORS PUT from the app origin, e.g.:
  gsutil cors set cors.json gs://<bucket>      # cors.json: [{"origin":["https://cookcredit.com"],"method":["PUT"],"responseHeader":["Content-Type"],"maxAgeSeconds":3600}]
Until that is set, callers fall back to proxying the upload through the API.
"""
import uuid
from datetime import timedelta
from urllib.parse import quote

from services.firebase import get_storage_bucket
from services.storage_signing import signed_url


def firebase_download_url(bucket, blob_name: str, token: str) -> str:
    """Token-based public download URL (same shape as web getDownloadURL())."""
    encoded = quote(blob_name, safe="")
    return (f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}"
            f"/o/{encoded}?alt=media&token={token}")


def signed_upload_url(path: str, content_type: str, ttl_minutes: int = 15) -> dict:
    """Mint a v4 signed PUT URL for a direct browser->Storage upload.

    Returns {upload_url, path, download_url, token}. The client must PUT with
    header `Content-Type: <content_type>` (it's part of the signature). After the
    PUT, the file is reachable at download_url (the firebase token is pre-seeded
    in object metadata via x-goog-meta on the signed PUT)."""
    bucket = get_storage_bucket()
    blob = bucket.blob(path)
    token = str(uuid.uuid4())
    upload_url = signed_url(blob,
        version="v4",
        method="PUT",
        expiration=timedelta(minutes=ttl_minutes),
        content_type=content_type,
        headers={"x-goog-meta-firebaseStorageDownloadTokens": token},
    )
    return {
        "upload_url": upload_url,
        "path": path,
        "download_url": firebase_download_url(bucket, path, token),
        "token": token,
    }


def upload_bytes(path: str, data: bytes, content_type: str) -> str:
    """Server-side upload fallback (proxy through the API). Returns download_url."""
    bucket = get_storage_bucket()
    blob = bucket.blob(path)
    token = str(uuid.uuid4())
    blob.upload_from_string(data, content_type=content_type)
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.patch()
    return firebase_download_url(bucket, path, token)


def detect_video_kind(header: bytes):
    """Identify a webm/mp4 clip from its magic bytes (never trust Content-Type).

    Returns 'webm' | 'mp4' | None. Shared by the routes that accept a video upload.
    """
    if header[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if header[4:8] == b"ftyp":
        return "mp4"
    return None
