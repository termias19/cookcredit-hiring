"""Private receipt photos. Reuse the bucket, never public Firebase tokens.

Reserve a durable upload row, return the connection, write the immutable object,
then finalize metadata. Failed/uncertain uploads remain attributable and retryable.
"""
import hashlib
import io
import uuid
from threading import BoundedSemaphore
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, func
from google.api_core.exceptions import PreconditionFailed
from models.home_service import HomeReceipt, HomeAccessAudit
from services.database import db_session
from services.firebase import get_storage_bucket
from services import home_visits as visits, home_quotes as quotes

MAX_BYTES = 8 * 1024 * 1024
# A compressed 20 MP PNG can expand into several pixel buffers. Bound this
# separately from request threads, before reserving a row or holding SQL.
_decode_gate = BoundedSemaphore(1)


def normalize(data):
    if not _decode_gate.acquire(blocking=False):
        visits.fail('receipt_processing_busy',
                    'Another receipt is being prepared. Please wait two seconds and retry.', 429)
    try:
        return _normalize(data)
    finally:
        _decode_gate.release()


def _normalize(data):
    if not data or len(data) > MAX_BYTES or not data.startswith((b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n')):
        visits.fail('invalid_receipt', 'Choose a JPEG or PNG receipt photo no larger than 8 MB.')
    try:
        with Image.open(io.BytesIO(data)) as check:
            if check.format not in ('JPEG','PNG') or check.width * check.height > 20000000 or getattr(check,'n_frames',1) != 1:
                raise ValueError()
            check.verify()
        with Image.open(io.BytesIO(data)) as source:
            ImageOps.exif_transpose(source, in_place=True)
            image = source
            image.thumbnail((3200,3200), Image.Resampling.LANCZOS)
            if image.mode in ('RGBA','LA'):
                rgba = image if image.mode == 'RGBA' else image.convert('RGBA')
                canvas = Image.new('RGB', rgba.size, 'white')
                canvas.paste(rgba, mask=rgba.getchannel('A'))
                image = canvas
            else:
                image = image.convert('RGB')
            output = io.BytesIO()
            image.save(output, 'JPEG', quality=90, optimize=True)
            encoded = output.getvalue()
        if len(encoded) > MAX_BYTES:
            raise ValueError()
        return encoded
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        visits.fail('invalid_receipt', 'This photo could not be read. Choose a clear, standard-size JPEG or PNG.')


def receipt_dict(row):
    return {'id':str(row.id), 'quoteId':str(row.quote_id), 'status':row.status,
            'bytes':row.size_bytes, 'contentType':row.content_type, 'uploadedBy':row.uploaded_by,
            'createdAt':row.created_at.isoformat()}


def upload(principal, booking_id, key, data, operator):
    if not isinstance(key,str) or len(key)<16 or len(key)>128:
        visits.fail('idempotency_key_required','A receipt upload reference is required.')
    raw_hash = hashlib.sha256(data).hexdigest()
    encoded = normalize(data)
    digest = hashlib.sha256(encoded).hexdigest()
    request_hash = visits.fingerprint({'actor':principal['uid'],'booking':booking_id,'key':key})
    with db_session() as session:
        booking, visit = visits.load_visit(session, booking_id, principal['uid'], operator, lock=True)
        if not operator and principal['uid'] != booking['cook_id']:
            visits.fail('forbidden','Only the assigned helper or CookCredit can upload purchase evidence.',403)
        if not visit.quote_id or booking['status'] == 'cancelled':
            visits.fail('receipt_not_ready','An agreed quote is required before uploading receipts.',409)
        row = session.execute(select(HomeReceipt).where(HomeReceipt.request_hash==request_hash)).scalar_one_or_none()
        if row:
            if row.original_hash != raw_hash:
                visits.fail('idempotency_conflict','This upload reference was used for a different photo.',409)
            if row.status == 'ready':
                return receipt_dict(row)
            if row.quote_id != visit.quote_id or not row.object_path.endswith('/'+digest+'.jpg'):
                visits.fail('receipt_changed','The quote or photo format changed. Upload this photo with a new reference.',409)
        else:
            count = session.execute(select(func.count(HomeReceipt.id)).where(HomeReceipt.booking_id==booking['id'],HomeReceipt.status!='failed')).scalar()
            if count >= 20:
                visits.fail('receipt_limit','This visit already has twenty receipt photos.',409)
            evidence_id = uuid.uuid4()
            row = HomeReceipt(id=evidence_id,booking_id=booking['id'],quote_id=visit.quote_id,
                uploaded_by=principal['uid'], request_hash=request_hash,original_hash=raw_hash,
                object_path=f'home_receipts/{booking["id"]}/{evidence_id}/{digest}.jpg',
                status='uploading', content_type='image/jpeg',size_bytes=0)
            session.add(row)
        session.flush()
    # Row reservation commits before storage I/O. No orphan can become an
    # untracked public attachment; generation preconditions make retry immutable.
    blob = get_storage_bucket().blob(row.object_path)
    try:
        blob.upload_from_string(encoded,content_type='image/jpeg',if_generation_match=0,timeout=20)
    except PreconditionFailed:
        blob.reload(timeout=5)
    if (int(blob.size or 0) != len(encoded) or blob.content_type != 'image/jpeg'
        or not str(blob.generation or '').isdigit() or int(blob.generation)<=0):
        visits.fail('receipt_unavailable','The receipt could not be verified. Please retry.',503)
    with db_session() as session:
        booking,visit=visits.load_visit(session,booking_id,principal['uid'],operator,lock=True)
        current = session.get(HomeReceipt,row.id,with_for_update=True)
        if booking['status']=='cancelled' or visit.quote_id!=current.quote_id:
            visits.fail('receipt_changed','The visit or quote changed while uploading. Refresh the visit.',409)
        if current.status=='ready':
            return receipt_dict(current)
        current.generation,current.sha256,current.size_bytes,current.status = str(blob.generation),digest,len(encoded),'ready'
        session.add(HomeAccessAudit(actor_id=principal['uid'], action='receipt_uploaded',subject_id=str(current.id)))
        session.flush()
        return receipt_dict(current)


def _blob(row):
    expected=f'home_receipts/{row.booking_id}/{row.id}/{row.sha256}.jpg'
    if row.status!='ready' or row.object_path!=expected or not str(row.generation or '').isdigit():
        visits.fail('receipt_unavailable','This receipt photo is not available.',409)
    return get_storage_bucket().blob(expected,generation=int(row.generation))


def verified_references(booking_id,quote_id,lines):
    if not isinstance(lines,list) or len(lines)>20:
        visits.fail('invalid_receipts','Check the material receipt lines.')
    keys={quotes.identifier(line['receiptReference']) for line in lines if isinstance(line,dict) and line.get('actualCents',0) and line.get('receiptReference')}
    if not keys:
        return {}
    with db_session() as session:
        rows=session.execute(select(HomeReceipt).where(HomeReceipt.id.in_(keys),HomeReceipt.booking_id==quotes.identifier(booking_id),HomeReceipt.quote_id==quotes.identifier(quote_id))).scalars().all()
    if {row.id for row in rows}!=keys:
        visits.fail('receipt_scope','Each purchase needs a receipt uploaded for this visit and quote.')
    def verify(row):
        blob=_blob(row)
        try:
            blob.reload(timeout=5)
        except Exception:
            visits.fail('receipt_unavailable','A receipt photo is missing. Upload it again before reconciling.',409)
        if int(blob.size or 0)!=row.size_bytes or str(blob.generation)!=row.generation or blob.content_type!=row.content_type:
            visits.fail('receipt_unavailable','A receipt photo could not be verified.',409)
        return str(row.id), {'generation':row.generation,'sha256':row.sha256}
    # SQL connections are released before bounded parallel storage metadata I/O.
    with ThreadPoolExecutor(max_workers=min(4,len(rows))) as pool:
        return dict(pool.map(verify,rows))


def read(principal,booking_id,receipt_id,operator):
    with db_session() as session:
        booking,visit=visits.load_visit(session,booking_id,principal['uid'],operator)
        row=session.get(HomeReceipt,quotes.identifier(receipt_id))
        if not row or row.booking_id!=booking['id']:
            visits.fail('not_found','Receipt not found.',404)
        session.add(HomeAccessAudit(actor_id=principal['uid'],action='receipt_viewed',subject_id=str(row.id)))
    data=_blob(row).download_as_bytes(timeout=15)
    if len(data)!=row.size_bytes or hashlib.sha256(data).hexdigest()!=row.sha256:
        visits.fail('receipt_unavailable','This receipt could not be verified.',409)
    return row,data
