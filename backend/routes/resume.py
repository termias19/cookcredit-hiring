"""
Resume parse — POST /api/resume/parse. Accepts a pasted `text` (JSON) or an uploaded `file`
(PDF/DOCX/TXT), extracts text, runs the canonical taxonomy trie, and returns job-related
key-points. ONLY job-related fields are extracted/stored — never name/photo/age/school/address
(fairness; see ELITE_B2B_DESIGN.md). Stores a versioned, file-hash-deduped snapshot per cook.
"""
import hashlib
import io
import logging

from flask import Blueprint, jsonify, request, g

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from services.taxonomy import scan_text, TAXONOMY_VERSION
from models import ResumeKeypoints

log = logging.getLogger(__name__)
resume_bp = Blueprint("resume", __name__)

MAX_BYTES = 6 * 1024 * 1024
MAX_TEXT = 60000


def _extract_text(file_storage):
    name = (file_storage.filename or "").lower()
    data = file_storage.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return None, "File too large"
    if name.endswith(".txt"):
        return data.decode("utf-8", "ignore"), None
    if name.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
            with fitz.open(stream=data, filetype="pdf") as doc:
                return "\n".join(page.get_text() for page in doc), None
        except ImportError:
            return None, "PDF parsing isn't available on the server — paste the text instead"
    if name.endswith(".docx"):
        try:
            import docx
            d = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in d.paragraphs), None
        except ImportError:
            return None, "DOCX parsing isn't available on the server — paste the text instead"
    return None, "Unsupported file type — use PDF, DOCX, or TXT"


@resume_bp.route("/parse", methods=["POST"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def parse_resume():
    if "file" in request.files:
        text, err = _extract_text(request.files["file"])
        if err:
            return jsonify({"error": err}), 400
    else:
        data = request.get_json(silent=True) or {}
        text = data.get("text") or ""

    text = (text or "")[:MAX_TEXT]
    if not text.strip():
        return jsonify({"error": "No resume text found"}), 400

    points = scan_text(text)
    file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Versioned snapshot per cook; skip a write if the exact text was already parsed (dedupe).
    with db_session() as session:
        existing = (session.query(ResumeKeypoints)
                    .filter_by(cook_id=g.user_id)
                    .order_by(ResumeKeypoints.version.desc())
                    .first())
        if not (existing and existing.file_hash == file_hash):
            version = (existing.version + 1) if existing else 1
            session.add(ResumeKeypoints(
                cook_id=g.user_id, version=version, points=points, file_hash=file_hash,
                taxonomy_version=TAXONOMY_VERSION, model_version="trie-1.0"))

    return jsonify({"points": points, "taxonomyVersion": TAXONOMY_VERSION}), 200
