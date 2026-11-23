"""Owner read model over existing Home accounts, interests, visits and calls.

One row per Firebase UID. Anonymous calls are contact-request groups, never new
accounts. A name/phone match alone cannot merge identities or grant any access.
"""
import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select, text, update
from models.home_service import HomeCallback, HomeCustomerFollowup
from services import home_visits as visits, home_customers as customers

CONTACT_NAME = "lower(regexp_replace(btrim(name),'[[:space:]]+',' ','g'))"
STATUSES = ('new', 'contacted', 'waiting', 'done')

# The existing customer/calendar indexes bound per-account lookups. Pagination
# happens after the union, so callbacks cannot disappear between two pagers.
# Only summaries enter this list: no addresses, household notes or medical text.
WORKLIST = r"""
WITH accounts AS (
 SELECT u.id AS uid,u.email,
   COALESCE(NULLIF(btrim(h.instructions->'enrollment'->>'name'),''),
     NULLIF(CASE WHEN u.name<>u.email THEN btrim(u.name) END,''),NULLIF(f.contact_name,''),'Name not provided') AS name,
   CASE WHEN NULLIF(btrim(h.instructions->'enrollment'->>'name'),'') IS NOT NULL THEN 'customer'
     WHEN NULLIF(CASE WHEN u.name<>u.email THEN btrim(u.name) END,'') IS NOT NULL THEN 'account'
     WHEN NULLIF(f.contact_name,'') IS NOT NULL THEN 'owner' ELSE 'missing' END AS name_source,
   h.instructions->'enrollment' AS interest,
   COALESCE(h.instructions->'enrollment'->>'status','')='withdrawn' AS withdrawn,
   COALESCE(h.instructions->'enrollment'->>'service' IN ('cooking','cleaning','both','not_sure'),false)
     AND COALESCE(h.instructions->'enrollment'->>'status','')<>'withdrawn' AS enrolled,
   COALESCE(f.version,0) AS version,COALESCE(f.status,'new') AS saved_status,f.activity_at AS handled_at,
   greatest(COALESCE(u.created_at,'1970-01-01'::timestamptz),i.created_at,v.activity_at,c.activity_at) AS activity_at,
   COALESCE(v.total,0) AS visit_count,COALESCE(v.active,0) AS active_visits,COALESCE(v.issue_open,false) AS issue_open,
   chosen.id AS visit_id,chosen.status AS visit_status,chosen.service AS visit_service,
   chosen.scheduled_date,chosen.scheduled_start_time,chosen.time_zone,chosen.recipient->>'name' AS recipient_name,
   COALESCE(c.total,0) AS call_total,COALESCE(c.active,0) AS call_count,
   call.id AS call_id,call.name AS call_name,call.phone AS call_phone,call.preferred_time,call.status AS call_status,
   call_revision.revision AS call_revision
 FROM users u
 LEFT JOIN home_households h ON h.user_id=u.id
 LEFT JOIN home_customer_followups f ON f.user_id=u.id
 LEFT JOIN LATERAL (
   SELECT created_at FROM home_events WHERE actor_id=u.id
     AND action IN ('service_interest_saved','service_interest_removed') ORDER BY created_at DESC,id DESC LIMIT 1
 ) i ON true
 LEFT JOIN LATERAL (
   SELECT count(*) AS total,count(*) FILTER(WHERE b.status NOT IN ('completed','cancelled')) AS active,
     bool_or(hv.issue_open) AS issue_open,max(b.created_at) AS activity_at
   FROM bookings b JOIN home_visits hv ON hv.booking_id=b.id WHERE b.eater_id=u.id
 ) v ON true
 LEFT JOIN LATERAL (
   SELECT b.id,b.status,hv.service,b.scheduled_date,b.scheduled_start_time,hv.time_zone,hv.recipient
   FROM bookings b JOIN home_visits hv ON hv.booking_id=b.id WHERE b.eater_id=u.id
   ORDER BY hv.issue_open DESC,(b.status NOT IN ('completed','cancelled')) DESC,b.created_at DESC,b.id DESC LIMIT 1
 ) chosen ON true
 LEFT JOIN LATERAL (
   SELECT count(*) AS total,count(*) FILTER(WHERE status<>'closed') AS active,max(created_at) AS activity_at,
     (array_agg(id ORDER BY (status<>'closed') DESC,created_at DESC,id DESC))[1] AS head
   FROM home_callbacks WHERE owner_customer_id=u.id
 ) c ON true
 LEFT JOIN home_callbacks call ON call.id=c.head
 LEFT JOIN LATERAL (
   SELECT md5(string_agg(id::text||':'||version::text,',' ORDER BY id)) AS revision FROM home_callbacks
   WHERE owner_customer_id=u.id AND phone=call.phone
     AND lower(regexp_replace(btrim(name),'[[:space:]]+',' ','g'))=lower(regexp_replace(btrim(call.name),'[[:space:]]+',' ','g'))
 ) call_revision ON true
 WHERE u.id<>'system:home' AND (:customer_id IS NULL OR u.id=:customer_id)
   AND (h.user_id IS NOT NULL OR v.total>0 OR c.total>0 OR EXISTS(
     SELECT 1 FROM home_events WHERE actor_id=u.id AND action='home_account_created'))
), classified AS (
 SELECT *,CASE WHEN handled_at IS NULL OR activity_at>handled_at OR issue_open THEN 'new' ELSE saved_status END AS followup
 FROM accounts
), callback_groups AS (
 SELECT phone,lower(regexp_replace(btrim(name),'[[:space:]]+',' ','g')) AS name_key,
   count(*) AS total,count(*) FILTER(WHERE status<>'closed') AS active,max(created_at) AS activity_at,
   (array_agg(id ORDER BY created_at,id))[1] AS anchor,
   (array_agg(id ORDER BY (status<>'closed') DESC,created_at DESC,id DESC))[1] AS head,
   md5(string_agg(id::text||':'||version::text,',' ORDER BY id)) AS revision
 FROM home_callbacks WHERE owner_customer_id IS NULL AND :customer_id IS NULL
 GROUP BY phone,lower(regexp_replace(btrim(name),'[[:space:]]+',' ','g'))
), people AS (
 SELECT 'u:'||uid AS id,activity_at,'customer' AS kind,
   (enrolled OR visit_count>0 OR call_total>0) AS has_request,
   (enrolled OR active_visits>0 OR call_count>0 OR issue_open) AND followup<>'done' AS needs_work,
   jsonb_build_object('id','u:'||uid,'kind','customer','customerId',uid,'name',name,'nameMissing',name='Name not provided','nameSource',name_source,
     'email',email,'phone',COALESCE(CASE WHEN enrolled THEN NULLIF(interest->>'phone','') END,CASE WHEN call_count>0 THEN call_phone END),
     'service',CASE WHEN enrolled THEN interest->>'service' END,'withdrawn',withdrawn,
     'canContact',enrolled OR active_visits>0 OR call_count>0 OR issue_open,
     'status',followup,'version',version,'activityAt',activity_at,'issueOpen',issue_open,
     'visitCount',visit_count,'activeVisits',active_visits,'callbackCount',call_count,'callbackTotal',call_total,
     'visit',CASE WHEN visit_id IS NOT NULL THEN jsonb_build_object('id',visit_id,'status',visit_status,
       'service',visit_service,'date',scheduled_date,'time',scheduled_start_time,'timeZone',time_zone,'recipientName',recipient_name) END,
     'callback',CASE WHEN call_id IS NOT NULL THEN jsonb_build_object('id',call_id,'name',call_name,'phone',call_phone,
       'preferredTime',preferred_time,'status',call_status,'groupVersion',call_revision) END) AS document
 FROM classified
 UNION ALL
 SELECT 'c:'||g.anchor::text,g.activity_at,'callback',true,g.active>0,
   jsonb_build_object('id','c:'||g.anchor::text,'kind','callback','name',c.name,'nameMissing',false,
     'email',NULL,'phone',c.phone,'service',NULL,'withdrawn',false,'canContact',g.active>0,
     'status',CASE WHEN g.active=0 THEN 'done' WHEN c.status='requested' THEN 'new' ELSE 'contacted' END,
     'activityAt',g.activity_at,'issueOpen',false,'visitCount',0,'activeVisits',0,'callbackCount',g.active,'callbackTotal',g.total,
     'visit',NULL,'callback',jsonb_build_object('id',c.id,'name',c.name,'phone',c.phone,
       'preferredTime',c.preferred_time,'status',c.status,'groupVersion',g.revision))
 FROM callback_groups g JOIN home_callbacks c ON c.id=g.head
)
SELECT id,activity_at,document FROM people
 WHERE (:scope='all' OR (:scope='needs' AND needs_work) OR (:scope='accounts' AND kind='customer' AND NOT has_request))
 AND (:query='' OR COALESCE(document->>'name','') ILIKE :pattern ESCAPE '!'
   OR COALESCE(document->>'email','') ILIKE :pattern ESCAPE '!'
   OR COALESCE(document->>'phone','') ILIKE :pattern ESCAPE '!')
 AND (:cursor_at IS NULL OR (activity_at,id)<(:cursor_at, :cursor_id))
 ORDER BY activity_at DESC,id DESC LIMIT 51
"""


def search(session, body, *, customer_id=None):
    visits.strict_object(body, (), ('query','scope','cursor'))
    query=body.get('query','');scope=body.get('scope','needs')
    if not isinstance(query,str) or len(query)>100 or scope not in ('needs','all','accounts'):
        visits.fail('invalid_search','Enter a name, email or phone number, and choose a list.')
    query=query.strip();signature=hashlib.sha256(json.dumps([query,scope]).encode()).hexdigest()[:16]
    at=key=None
    if body.get('cursor'):
        try:
            token=body['cursor']
            if not isinstance(token,str) or len(token)>512:raise ValueError()
            decoded=json.loads(base64.urlsafe_b64decode(token+'='*((-len(token))%4)))
            at=datetime.fromisoformat(decoded['at']);key=decoded['id']
            if at.tzinfo is None or decoded['query']!=signature or not isinstance(key,str) or len(key)>150:raise ValueError()
        except (ValueError,TypeError,KeyError,binascii.Error,UnicodeError):
            visits.fail('invalid_cursor','Refresh this customer list.')
    pattern='%'+query.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
    rows=session.execute(text(WORKLIST),{'customer_id':customer_id,'scope':scope,'query':query,'pattern':pattern,
        'cursor_at':at,'cursor_id':key}).mappings().all()
    cursor=None
    if len(rows)>50:
        last=rows[49]
        cursor=base64.urlsafe_b64encode(json.dumps({'at':last['activity_at'].isoformat(),'id':last['id'],'query':signature}).encode()).decode().rstrip('=')
    return {'people':[row['document']for row in rows[:50]],'nextCursor':cursor}


def lock_customer(session,uid):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'home-followup:'+uid})


def reopen_for_request(session,uid):
    # PostgreSQL now() uses transaction start, not commit time. A request can
    # commit after the owner finishes work while carrying an older timestamp.
    # Serialize it with follow-up and advance its version independently of time.
    lock_customer(session,uid)
    session.execute(update(HomeCustomerFollowup).where(HomeCustomerFollowup.user_id==uid)
        .values(status='new',version=HomeCustomerFollowup.version+1,
            updated_by=uid,updated_at=datetime.now(timezone.utc)))


def lock_contact(session,phone,name):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('home-call-contact:'||:phone||':'||"
        "lower(regexp_replace(btrim(:name),'[[:space:]]+',' ','g')),0))"),{'phone':phone,'name':name})


def save_followup(session,actor,uid,body):
    visits.strict_object(body,('status','version','activityAt'),('name',))
    if body['status'] not in STATUSES or type(body['version'])is not int:
        visits.fail('invalid_followup','Choose a follow-up status.')
    lock_customer(session,uid)
    found=search(session,{'scope':'all'},customer_id=uid)['people']
    if not found:visits.fail('not_found','This Home customer was not found.',404)
    current=found[0]
    if current['version']!=body['version'] or current['activityAt']!=body['activityAt']:
        visits.fail('stale_version','A request or follow-up changed. Refresh before saving.',409)
    if body['status']=='done'and current['issueOpen']:
        visits.fail('stale_version','Review the open visit issue before finishing follow-up.',409)
    name=None
    if 'name'in body:
        if current['nameSource']not in ('missing','owner'):
            visits.fail('invalid_followup','This customer already supplied their name. Refresh the list before editing.')
        name=' '.join(visits.bounded_text(body['name'],'the confirmed name',120,required=True).split())
    row=session.get(HomeCustomerFollowup,uid)
    if row is None:
        row=HomeCustomerFollowup(user_id=uid,version=0)
        session.add(row)
    row.status=body['status'];row.version+=1
    if name is not None:row.contact_name=name
    row.activity_at=datetime.fromisoformat(current['activityAt']);row.updated_at=datetime.now(timezone.utc);row.updated_by=actor['uid']
    if row.status=='done':
        # The shared customer lock also protects authenticated callback inserts
        # and owner links. Completing contact work never completes a visit.
        session.execute(update(HomeCallback).where(HomeCallback.owner_customer_id==uid,HomeCallback.status!='closed')
            .values(status='closed',version=HomeCallback.version+1))
    customers.audit(session,actor,'customer_followup_'+row.status,uid)
    if name is not None:customers.audit(session,actor,'customer_name_recorded',uid)
    return {'updated':True,'version':row.version}


def callback_followup(session,actor,callback_id,body):
    from services.home_quotes import identifier
    visits.strict_object(body,('action','groupVersion'),('customerId','confirmedSamePerson'))
    action=body['action']
    if action not in ('contacting','closed','link','unlink'):
        visits.fail('invalid_followup','Choose a call-request action.')
    first=session.get(HomeCallback,identifier(callback_id))
    if first is None:visits.fail('not_found','This call request was not found.',404)
    target=body.get('customerId')if action=='link'else first.owner_customer_id
    if target:
        if not isinstance(target,str) or len(target)>128:visits.fail('invalid_followup','Choose an existing customer.')
        lock_customer(session,target)
    lock_contact(session,first.phone,first.name)
    owner_id=first.owner_customer_id
    rows=session.execute(select(HomeCallback).where(HomeCallback.phone==first.phone,
        text(CONTACT_NAME+"=lower(regexp_replace(btrim(:contact_name),'[[:space:]]+',' ','g'))"),
        HomeCallback.owner_customer_id==owner_id if owner_id else HomeCallback.owner_customer_id.is_(None))
        .order_by(HomeCallback.id).with_for_update().execution_options(populate_existing=True),{'contact_name':first.name}).scalars().all()
    if not rows or not any(row.id==first.id for row in rows):visits.fail('stale_version','This call request changed. Refresh.',409)
    version=hashlib.md5(','.join(f'{row.id}:{row.version}'for row in rows).encode(),usedforsecurity=False).hexdigest()
    if version!=body['groupVersion']:visits.fail('stale_version','A call request changed. Refresh before saving.',409)
    if action=='link':
        if owner_id or body.get('confirmedSamePerson')is not True or not target or not search(session,{'scope':'all'},customer_id=target)['people']:
            visits.fail('invalid_followup','Choose an existing Home account and confirm this is the same person.')
        # Linking an older open request must reopen work already marked done.
        # Its original creation time can precede the last handled snapshot.
        followup=session.get(HomeCustomerFollowup,target)
        if followup is not None and any(row.status!='closed' for row in rows):
            followup.status='new';followup.version+=1
            followup.updated_by=actor['uid'];followup.updated_at=datetime.now(timezone.utc)
    if action=='unlink'and not owner_id:visits.fail('stale_version','This request is already separate.',409)
    for row in rows:
        if action in ('link','unlink'):row.owner_customer_id=target if action=='link'else None
        else:row.status=action
        row.version+=1
    customers.audit(session,actor,'callback_group_'+action,first.id)
    return {'updated':True,'requests':len(rows)}
