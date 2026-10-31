"""Connected customer/helper/support APIs. No Hiring company approval is reused."""
import io
import os
import uuid
from flask import Blueprint,jsonify,request,g,send_file
from sqlalchemy import select,update
from extensions import limiter
from middleware.auth import require_identity
from middleware.app_check import require_app_check
from models import User,CookProfile
from models.home_service import HomeHelperPermission,HomeCallback,HomeReceipt,HomeAccessAudit
from services.database import db_session
from services import home_customers as customers,home_visits as visits,home_quotes as quotes,home_payments as payments,home_stripe
from routes.home_visits import home_auth,is_owner,is_operator,principal,json_body,emails

customer_bp=Blueprint('home_customers',__name__)


@customer_bp.route('/operating-rules',methods=['GET','PUT'])
@home_auth
@limiter.limit('12 per minute',key_func=lambda:g.user_id)
def operating_rules():
    if not is_owner():
        visits.fail('forbidden','Only the Home owner can manage operating rules.',403)
    from services import home_operating_rules as rules
    with db_session() as session:
        if request.method=='GET':
            result=rules.draft(session)
            customers.audit(session,principal(),'operating_rules_viewed','draft')
        else:
            actor,body=principal(),json_body()
            result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'operating-rules',body,
                lambda:rules.save(session,actor,body))
    return jsonify(result)


@customer_bp.route('/enrollment',methods=['GET','PUT','DELETE'])
@home_auth
@limiter.limit('20 per minute',key_func=lambda:g.user_id)
def enrollment():
    with db_session() as session:
        if request.method=='GET':
            result={'enrollment':customers.enrollment(session,g.user_id)}
        else:
            body,actor=json_body(),principal()
            result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'enrollment:'+request.method,body,
                lambda:customers.save_enrollment(session,actor,body) if request.method=='PUT' else customers.withdraw_enrollment(session,actor,body))
    return jsonify(result)


@customer_bp.get('/enrollments')
@home_auth
@limiter.limit('30 per minute',key_func=lambda:g.user_id)
def enrollments():
    # The owner's directory includes people who have not booked yet. Home
    # operator/helper access does not grant access to these contact details.
    if not is_owner():
        visits.fail('forbidden','Only the Home owner can view enrollments.',403)
    with db_session() as session:
        result=customers.list_enrollments(session,request.args.get('cursor'))
        customers.audit(session,principal(),'enrollment_list_viewed','directory')
    return jsonify(result)


@customer_bp.post('/account/verification')
@require_identity
@require_app_check
@limiter.limit('6 per hour',key_func=lambda:g.user_id)
def verification():
    body=json_body();visits.strict_object(body,(),('returnTo',))
    target=customers.return_route(body.get('returnTo'))
    if g.email_verified:
        return jsonify(alreadyVerified=True)
    if os.getenv('HOME_EMAILS_ENABLED')!='1':
        visits.fail('email_unavailable','Email delivery is not enabled yet. Please use Google sign-in or contact support.',503)
    if os.getenv('COOKCREDIT_ENVIRONMENT')=='staging' and g.email.casefold() not in emails('HOME_ACCEPTANCE_EMAILS'):
        visits.fail('private_acceptance','Use an account enabled for private Home acceptance.',403)
    from services.account_email import enqueue_account_email
    with db_session() as session:
        result=enqueue_account_email(session,kind='verify',recipient=g.email,user_id=g.user_id,content={'homeReturn':target})
    return jsonify(result),202


@customer_bp.post('/account/reset')
@require_app_check
@limiter.limit('3 per hour')
def password_reset():
    from services.hiring_access import normalize_email
    from services.account_email import enqueue_account_email
    body=json_body();visits.strict_object(body,('email',),('returnTo',))
    target=customers.return_route(body.get('returnTo'))
    try:
        email=normalize_email(body['email'])
    except ValueError:
        visits.fail('invalid_email','Enter a valid email address.')
    if os.getenv('COOKCREDIT_ENVIRONMENT')!='staging' or email in emails('HOME_ACCEPTANCE_EMAILS'):
        if os.getenv('HOME_EMAILS_ENABLED')=='1':
            with db_session() as session:
                enqueue_account_email(session,kind='reset',recipient=email,content={'homeReturn':target})
    return jsonify(queued=True),202


@customer_bp.get('/household')
@home_auth
def household():
    with db_session() as session:
        result=customers.household(session,g.user_id)
    return jsonify(household=result)


@customer_bp.route('/household',methods=['PUT','DELETE'])
@home_auth
@limiter.limit('12 per hour',key_func=lambda:g.user_id)
def change_household():
    body,actor=json_body(),principal()
    with db_session() as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'household:'+request.method,body,
            lambda:customers.save_household(session,actor,body) if request.method=='PUT' else customers.remove_household(session,actor,body))
    return jsonify(result)


@customer_bp.post('/callbacks')
@require_app_check
@limiter.limit('3 per hour')
def request_callback():
    # Private staging must not collect real anonymous household requests.
    if os.getenv('COOKCREDIT_ENVIRONMENT')=='staging':
        return home_auth(_request_callback)()
    return _request_callback()


def _request_callback():
    with db_session() as session:
        result=customers.create_callback(session,json_body())
    return jsonify(result),202


@customer_bp.get('/callbacks')
@home_auth
def callbacks():
    if not is_operator():
        visits.fail('forbidden','CookCredit operator access is required.',403)
    with db_session() as session:
        rows=session.execute(select(HomeCallback).where(HomeCallback.status!='closed').order_by(HomeCallback.created_at.desc()).limit(50)).scalars().all()
        customers.audit(session,principal(),'callback_queue_viewed','queue')
        result=[{'id':str(row.id),'name':row.name,'phone':row.phone,'preferredTime':row.preferred_time,
            'status':row.status,'version':row.version} for row in rows]
    return jsonify(callbacks=result)


@customer_bp.post('/callbacks/<callback_id>')
@home_auth
def callback_update(callback_id):
    if not is_operator():
        visits.fail('forbidden','CookCredit operator access is required.',403)
    body,actor=json_body(),principal()
    visits.strict_object(body,('version','status'))
    if body['status'] not in ('contacting','closed') or type(body['version'])is not int:
        visits.fail('invalid_status','Choose contacting or closed.')
    def change(session):
        row=session.get(HomeCallback,quotes.identifier(callback_id),with_for_update=True)
        if not row:
            visits.fail('not_found','Callback not found.',404)
        if row.version!=body['version']:
            visits.fail('stale_version','This callback changed. Refresh the queue.',409)
        row.version+=1;row.status=body['status']
        customers.audit(session,actor,'callback_'+body['status'],row.id)
        return {'updated':True,'version':row.version}
    with db_session() as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'callback:'+callback_id,body,lambda:change(session))
    return jsonify(result)


@customer_bp.post('/helpers/apply')
@home_auth
@limiter.limit('6 per hour',key_func=lambda:g.user_id)
def helper_apply():
    body,actor=json_body(),principal()
    with db_session() as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'helper-application',body,
            lambda:customers.helper_application(session,actor,body))
    return jsonify(result),202


@customer_bp.get('/helpers')
@home_auth
def helpers():
    if not is_operator():
        visits.fail('forbidden','CookCredit operator access is required.',403)
    with db_session() as session:
        rows=session.execute(select(User.id,User.name,CookProfile.bio,CookProfile.specialties,CookProfile.approved,HomeHelperPermission)
            .join(CookProfile,CookProfile.user_id==User.id).outerjoin(HomeHelperPermission,HomeHelperPermission.user_id==User.id)
            .where(CookProfile.applied_at.is_not(None)).order_by(CookProfile.applied_at.desc()).limit(100)).all()
        result=[{'id':row.id,'name':row.name,'bio':row.bio,'requestedServices':row.specialties,
            'enabled':bool(row.HomeHelperPermission and row.HomeHelperPermission.enabled),
            'cooking':bool(row.approved and row.HomeHelperPermission and row.HomeHelperPermission.cooking),
            'cleaning':bool(row.HomeHelperPermission and row.HomeHelperPermission.cleaning)} for row in rows]
    return jsonify(helpers=result)


@customer_bp.post('/helpers/<helper_id>/review')
@home_auth
def helper_review(helper_id):
    if not is_owner():
        visits.fail('forbidden','Only the Home owner can approve helpers.',403)
    body,actor=json_body(),principal()
    with db_session() as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'helper-review:'+helper_id,body,
            lambda:customers.review_helper(session,actor,helper_id,body))
    return jsonify(result)


@customer_bp.post('/payout-account')
@home_auth
def connect_account():
    if os.getenv('HOME_CONNECT_ENABLED')!='1':
        visits.fail('connect_disabled','Payout account setup is not enabled yet.',503)
    actor,body=principal(),json_body();visits.strict_object(body,())
    def create(session):
        permission=session.get(HomeHelperPermission,g.user_id)
        if not permission or not permission.enabled:
            visits.fail('helper_approval_required','CookCredit must approve your helper profile first.',403)
        account=session.execute(select(CookProfile.stripe_account_id).where(CookProfile.user_id==g.user_id)).scalar()
        if not account:
            payments.operation(session,payment=None,actor=g.user_id,kind='connect',suffix=str(home_stripe.mode()),
                payload={'helperId':g.user_id,'email':g.email,'livemode':home_stripe.mode()=='live'})
        return {'requested':True}
    with db_session() as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'connect',body,lambda:create(session))
    return jsonify(result),202


@customer_bp.get('/payout-account')
@home_auth
def payout_status():
    with db_session() as session:
        permission=session.get(HomeHelperPermission,g.user_id)
        if not permission or not permission.enabled:
            visits.fail('helper_approval_required','CookCredit helper access is required.',403)
        account_id=session.execute(select(CookProfile.stripe_account_id).where(CookProfile.user_id==g.user_id)).scalar()
    if not account_id:
        return jsonify(connected=False,enabled=os.getenv('HOME_CONNECT_ENABLED')=='1')
    value=home_stripe.StripeHome().account(account_id)
    if (value.get('metadata')or{}).get('home_helper_id')!=g.user_id:
        visits.fail('account_review_required','CookCredit must review the payout account binding.',409)
    ready=bool(value.get('payouts_enabled')and value.get('details_submitted')and(value.get('capabilities')or{}).get('transfers')=='active')
    with db_session() as session:
        session.execute(update(CookProfile).where(CookProfile.user_id==g.user_id).values(stripe_onboarded=ready))
    return jsonify(connected=True,payoutsEnabled=ready,requirements=(value.get('requirements')or{}).get('currently_due',[]))


@customer_bp.post('/payout-account/link')
@home_auth
def payout_link():
    body=json_body();visits.strict_object(body,('kind',))
    if body['kind']not in ('onboarding','dashboard'):
        visits.fail('invalid_link','Choose account setup or the Stripe dashboard.')
    with db_session() as session:
        permission=session.get(HomeHelperPermission,g.user_id)
        account=session.execute(select(CookProfile.stripe_account_id).where(CookProfile.user_id==g.user_id)).scalar()
        if not permission or not permission.enabled or not account:
            visits.fail('account_required','Start payout account setup first.',409)
    provider=home_stripe.StripeHome()
    if (provider.account(account).get('metadata')or{}).get('home_helper_id')!=g.user_id:
        visits.fail('account_review_required','CookCredit must review the payout account binding.',409)
    value=provider.onboarding(account)if body['kind']=='onboarding'else provider.dashboard(account)
    return jsonify(url=value['url'])


@customer_bp.post('/visits/<booking_id>/receipts')
@home_auth
@limiter.limit('20 per hour',key_func=lambda:g.user_id)
def upload_receipt(booking_id):
    from services.home_receipts import upload,MAX_BYTES
    request.max_content_length=MAX_BYTES+65536
    file=request.files.get('file')
    if file is None:
        visits.fail('receipt_required','Choose a receipt photo.')
    result=upload(principal(),booking_id,request.headers.get('Idempotency-Key'),file.stream.read(MAX_BYTES+1),is_operator())
    return jsonify(receipt=result),201


@customer_bp.get('/visits/<booking_id>/receipts')
@home_auth
def list_receipts(booking_id):
    from services.home_receipts import receipt_dict
    with db_session() as session:
        booking,visit=visits.load_visit(session,booking_id,g.user_id,is_operator())
        rows=session.execute(select(HomeReceipt).where(HomeReceipt.booking_id==booking['id']).order_by(HomeReceipt.created_at).limit(50)).scalars().all()
        result=[receipt_dict(row)for row in rows]
    return jsonify(receipts=result)


@customer_bp.get('/visits/<booking_id>/receipts/<receipt_id>')
@home_auth
def read_receipt(booking_id,receipt_id):
    from services.home_receipts import read
    row,data=read(principal(),booking_id,receipt_id,is_operator())
    response=send_file(io.BytesIO(data),mimetype='image/jpeg',as_attachment=True,download_name=f'cookcredit-receipt-{row.id}.jpg')
    response.headers['Content-Security-Policy']="default-src 'none'; sandbox"
    return response


@customer_bp.get('/audit')
@home_auth
def access_audit():
    if not is_owner():
        visits.fail('forbidden','Only the Home owner can view access audit records.',403)
    with db_session() as session:
        rows=session.execute(select(HomeAccessAudit).order_by(HomeAccessAudit.created_at.desc()).limit(100)).scalars().all()
        result=[{'actorId':row.actor_id,'action':row.action,'subjectId':row.subject_id,'at':row.created_at.isoformat()}for row in rows]
    return jsonify(events=result)
