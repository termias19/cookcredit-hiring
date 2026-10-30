"""Home-only customer preferences, callback intake and helper review."""
import re
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert
from models import User, EaterProfile, CookProfile
from models.home_service import HomeHousehold, HomeCallback, HomeHelperPermission, HomeAccessAudit
from services import home_visits as visits


def return_route(value=None):
    if value is None:
        return 'visits'
    if not isinstance(value,str) or not re.fullmatch(r'(request|visits|payout|team|helping|visit/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',value):
        visits.fail('invalid_return','Please reopen the account form from your visit.')
    return value


def audit(session,principal,action,subject):
    visits.sync_identity(session,principal,refresh=False)
    session.add(HomeAccessAudit(actor_id=principal['uid'],action=action,subject_id=str(subject)))


def household(session,uid):
    row=session.execute(select(EaterProfile.address_street,HomeHousehold).join(HomeHousehold,HomeHousehold.user_id==EaterProfile.user_id)
        .where(EaterProfile.user_id==uid)).first()
    return None if not row else {'address':row[0], 'instructions':row[1].instructions}


def save_household(session,principal,body):
    visits.strict_object(body,('address','instructions','remember'))
    if body['remember'] is not True:
        visits.fail('consent_required','Confirm that you want these details saved for future visits.')
    instructions=body['instructions']
    visits.strict_object(instructions,('preferences','cleaningTasks','visitNotes'))
    value={'preferences':visits.choices(instructions['preferences'],visits.PREFERENCES,'preferences'),
        'cleaningTasks':visits.choices(instructions['cleaningTasks'],visits.CLEANING_TASKS,'cleaning tasks'),
        'visitNotes':visits.bounded_text(instructions['visitNotes'],'household instructions',1000)}
    address=visits.bounded_text(body['address'],'your address',400,required=True)
    session.execute(insert(EaterProfile.__table__).values(user_id=principal['uid'],address_street=address)
        .on_conflict_do_update(index_elements=[EaterProfile.user_id],set_={'address_street':address}))
    session.execute(insert(HomeHousehold).values(user_id=principal['uid'],instructions=value)
        .on_conflict_do_update(index_elements=[HomeHousehold.user_id],set_={'instructions':value,'consented_at':datetime.now(timezone.utc)}))
    visits.event(session,principal['uid'],'household_saved')
    return {'saved':True}


def remove_household(session,principal,body):
    visits.strict_object(body,())
    session.execute(delete(HomeHousehold).where(HomeHousehold.user_id==principal['uid']))
    session.execute(update(EaterProfile.__table__).where(EaterProfile.user_id==principal['uid']).values(address_street=None))
    visits.event(session,principal['uid'],'household_removed')
    return {'removed':True}


def create_callback(session,body):
    visits.strict_object(body,('requestId','name','phone','preferredTime','contactConsent'),('website',))
    if body.get('website'):
        visits.fail('invalid_request','Please check the request.')
    if body['contactConsent'] is not True:
        visits.fail('consent_required','Confirm that CookCredit may call you about this request.')
    try:
        request_id=uuid.UUID(body['requestId'])
    except (ValueError,TypeError,AttributeError):
        visits.fail('invalid_reference','Please retry from the callback form.')
    phone=visits.bounded_text(body['phone'],'your phone number',40,required=True)
    if not re.fullmatch(r'[+()0-9 .-]+',phone):
        visits.fail('invalid_phone','Enter your phone number with its area code.')
    digits=re.sub(r'\D','',phone)
    if len(digits)==10:
        digits='1'+digits
    if not 11<=len(digits)<=15:
        visits.fail('invalid_phone','Enter your phone number with its area code.')
    name=visits.bounded_text(body['name'],'your name',120,required=True)
    preferred_time=visits.bounded_text(body['preferredTime'],'the best callback time',100,required=True)
    fingerprint=visits.fingerprint(body)
    # Serialize exactly this anonymous request reference; callers cannot change
    # its phone/name on a retry and notifications never run before commit.
    from sqlalchemy import text
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'home-callback:'+str(request_id)})
    existing=session.get(HomeCallback,request_id)
    if existing:
        if existing.fingerprint!=fingerprint:
            visits.fail('idempotency_conflict','This reference was used for a different callback request.',409)
        return {'id':str(existing.id),'status':'received'}
    row=HomeCallback(id=request_id,fingerprint=fingerprint,
        name=name,phone='+'+digits,preferred_time=preferred_time)
    session.add(row)
    visits.event(session,'system:home','callback_requested',callbackId=str(request_id))
    return {'id':str(request_id),'status':'received'}


def helper_application(session,principal,body):
    visits.strict_object(body,('bio','services','contactConsent'))
    if body['contactConsent'] is not True or body['services'] not in ('cooking','cleaning','both'):
        visits.fail('invalid_application','Choose your services and confirm contact permission.')
    bio=visits.bounded_text(body['bio'],'your experience',1000,required=True)
    statement=insert(CookProfile.__table__).values(user_id=principal['uid'],bio=bio,
        specialties=[body['services']],applied_at=datetime.now(timezone.utc),approved=False)
    session.execute(statement.on_conflict_do_update(index_elements=[CookProfile.user_id],
        set_={'bio':bio,'specialties':[body['services']],'applied_at':datetime.now(timezone.utc)}))
    visits.event(session,principal['uid'],'helper_application_received')
    return {'received':True}


def review_helper(session,principal,helper_id,body):
    visits.strict_object(body,('enabled','cooking','cleaning','reviewConfirmed'))
    if any(type(value)is not bool for value in body.values()) or body['reviewConfirmed'] is not True:
        visits.fail('review_required','Confirm that the helper and their service capabilities were reviewed.')
    profile=session.execute(select(CookProfile.user_id,CookProfile.applied_at).where(CookProfile.user_id==helper_id)).first()
    if not profile or not profile.applied_at:
        visits.fail('application_required','The helper must submit their Home application first.',409)
    session.execute(update(CookProfile.__table__).where(CookProfile.user_id==helper_id).values(approved=body['enabled']and body['cooking']))
    return visits.set_helper_permission(session,principal,helper_id,{key:body[key] for key in ('enabled','cooking','cleaning')})
