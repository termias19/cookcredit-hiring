"""Application-specific human review. Private notes never enter applicant views."""
from models import HiringApplicationEvent, User

STATES = {'reviewing', 'shortlisted', 'contacted', 'hired', 'not_selected'}
EVENTS = ('employer_review_saved', 'employer_update_published')

def latest_events(session, application_id):
    base = session.query(HiringApplicationEvent).filter(HiringApplicationEvent.application_id == application_id)
    latest = base.filter(HiringApplicationEvent.event_type.in_(EVENTS)).order_by(HiringApplicationEvent.created_at.desc(), HiringApplicationEvent.id.desc()).first()
    published = base.filter(HiringApplicationEvent.event_type == EVENTS[1]).order_by(HiringApplicationEvent.created_at.desc(), HiringApplicationEvent.id.desc()).first()
    return ([latest] if latest else []) + ([published] if published and (not latest or published.id != latest.id) else [])


def review_view(events, public=False, session=None):
    relevant = next((e for e in events if not public or e.event_type == EVENTS[1]), None)
    if not relevant: return None
    detail = relevant.detail or {}
    result = {'status': detail.get('status'), 'message': detail.get('message', ''),
              'updatedAt': relevant.created_at.isoformat() if relevant.created_at else None}
    if not public:
        result.update(revision=str(relevant.id), notes=detail.get('notes', ''),
                      reviewerId=relevant.actor_id, published=relevant.event_type == EVENTS[1])
    if not public and session is not None:
        reviewer = session.get(User, relevant.actor_id)
        result["reviewerName"] = reviewer.name if reviewer else "Company reviewer"
    return result

def validate_review(body):
    if not isinstance(body, dict) or set(body) - {'status','message','notes','publish','revision'}:
        raise ValueError('Invalid review fields')
    if not isinstance(body.get('status'), str) or body['status'] not in STATES or type(body.get('publish')) is not bool:
        raise ValueError('Choose a review status and save or publish')
    clean = {'status':body['status']}
    for key,limit in [('notes',5000),('message',2000)]:
        value=body.get(key,'')
        if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\r\t' for c in value):
            raise ValueError('Invalid '+key)
        clean[key]=value.strip()
    if body['publish'] and not clean['message']:
        raise ValueError('Write an applicant message before publishing')
    if body.get('revision') is not None and not isinstance(body['revision'],str):
        raise ValueError('Invalid review revision')
    return clean
