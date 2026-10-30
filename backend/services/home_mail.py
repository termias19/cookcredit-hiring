"""Home service messages on the existing account outbox and mail transport.

Domain events convert to mail only when queue capacity is available. A burst of
notifications cannot roll back a booking or consume verification's reserved slots.
No allergy, address, telephone, medical note or payment URL appears in email.
"""
import hashlib
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from models import User, Booking
from models.account_email import AccountEmail
from models.home_service import HomeEvent, HomeNotificationCursor
from services.database import db_session
from services import home_visits as visits

SUPPORT = 'connectwithus@cookcredit.com'
COPY = {
 'home_account_created':('Your CookCredit Home account is ready','Welcome to CookCredit Home','You can arrange cooking or cleaning, review your helper and full quote, and keep track of your visits.'),
 'visit_requested':('We received your Home visit request','Your request is with CookCredit','We will review your requirements and confirm availability. No payment has been taken for this request.'),
 'quote_issued':('A Home visit quote needs your review','Review the work and earnings','A quote is ready for your assigned visit. Read the agreed work, materials and earnings before accepting.'),
 'helper_quote_accepted':('Your full Home visit quote is ready','Review your full quote','Your helper accepted the itemized work. Review every cost and materials allowance before approving or paying.'),
 'payment_verified':('Your CookCredit Home payment was received','Payment confirmed','Stripe confirmed your payment. View the approved amount and visit details in your account. Unused materials and tax allowance are refunded after review.'),
 'finish':('Please confirm your Home visit','Your helper marked the work finished','Review the completed work and report any issue before confirming. The helper’s funds remain subject to completion and expense review.'),
 'refund_verified':('Your CookCredit Home refund was confirmed','Refund confirmed','Stripe confirmed a refund for this visit. View the amount in your account. Your bank determines when it appears.'),
 'helper_funds_transferred':('Your Home visit funds reached Stripe','Funds transferred to your Stripe balance','The transfer for this visit is recorded in your account. This is not confirmation of a bank payout. Open Stripe to check bank payout status.'),
 'helper_transfer_reversed':('A Home transfer is under review','Transfer returned for review','A transfer for this visit was returned to the platform for review. Contact CookCredit with questions.'),
 'cancel':('Your Home visit cancellation is recorded','Cancellation received','Your cancellation is recorded. If a payment needs a refund, its verified status will appear separately in your account.'),
 'report_issue':('A Home visit needs attention','An issue needs review','An issue was reported for a Home visit. Open the private queue to review it. New transfers are held; an existing transfer may need recovery.'),
 'payment_review_required':('A Home payment needs review','Review the payment state','A payment adjustment needs operator review. Funds remain held. Open the private visit record for details.'),
 'callback_requested':('A Home callback was requested','A callback needs follow-up','Someone requested telephone help. Open the private callback queue to read the contact details and record your follow-up.'),
 'helper_application_received':('A Home helper application needs review','Review a helper application','A helper submitted their Home service experience. Review their profile and capabilities before granting access.'),
}


def ensure_welcome(session,principal):
    statement=insert(HomeEvent).values(id=uuid.uuid4(),actor_id=principal['uid'],action='home_account_created',details={})
    session.execute(statement.on_conflict_do_nothing(index_elements=[HomeEvent.actor_id,HomeEvent.action],
        index_where=HomeEvent.action=='home_account_created'))
    session.info['home_dispatch_due']=datetime.now(timezone.utc)


def _recipients(session,event):
    if event.action in ('callback_requested','helper_application_received','report_issue','payment_review_required'):
        return [(SUPPORT,None)]
    if event.action=='home_account_created':
        user=session.get(User,event.actor_id)
        return [(user.email,user.id)] if user else []
    booking=session.execute(select(Booking.eater_id,Booking.cook_id).where(Booking.id==event.booking_id)).first()
    if not booking:
        return []
    uid=booking.cook_id if event.action in ('quote_issued','helper_funds_transferred','helper_transfer_reversed') else booking.eater_id
    user=session.get(User,uid) if uid else None
    return [(user.email,user.id)] if user else []


def convert_events(limit=20):
    if os.getenv('HOME_EMAILS_ENABLED')!='1':
        return {'converted':0}
    from services.email_capacity import reserve_email_slot, EmailQueueBusy
    count=0
    for _ in range(min(20,max(1,int(limit)))):
        try:
            with db_session() as session:
                row=session.execute(select(HomeNotificationCursor,HomeEvent).join(HomeEvent,HomeNotificationCursor.event_id==HomeEvent.id)
                    .where(HomeNotificationCursor.status=='pending').order_by(HomeNotificationCursor.created_at,HomeNotificationCursor.event_id)
                    .with_for_update(of=HomeNotificationCursor,skip_locked=True).limit(1)).first()
                if not row:
                    break
                cursor,event=row
                if event.action in COPY:
                    for recipient,uid in _recipients(session,event):
                        key=hashlib.sha256(f'home:{event.id}:{recipient}'.encode()).hexdigest()
                        if reserve_email_slot(session,key,maximum=90):
                            session.add(AccountEmail(dedupe_key=key,kind='home_notice',recipient=recipient,user_id=uid,
                                content={'action':event.action,'bookingId':str(event.booking_id) if event.booking_id else None}))
                cursor.status='done'
                count+=1
        except EmailQueueBusy:
            break
    return {'converted':count}


def deliver(item):
    from services.account_email import account_email_content,send_account_message,_action_link
    from services.firebase import get_auth
    base=os.environ['HOME_PUBLIC_URL'].rstrip('/')
    if os.getenv('COOKCREDIT_ENVIRONMENT')=='staging':
        allowed={value.strip().casefold() for value in os.getenv('HOME_ACCEPTANCE_EMAILS','').split(',') if value.strip()}
        if item.recipient.casefold() not in allowed|{SUPPORT}:
            return 'skipped'
    if item.user_id or item.kind=='reset':
        provider=get_auth()
        try:
            user=provider.get_user(item.user_id) if item.user_id else provider.get_user_by_email(item.recipient)
        except provider.UserNotFoundError:
            return 'skipped'
        if user.disabled or not user.email or user.email.casefold()!=item.recipient.casefold():
            return 'skipped'
        if item.kind=='verify' and user.email_verified:
            return 'skipped'
        if item.kind not in ('verify','reset') and not user.email_verified:
            return 'skipped'
    if item.kind in ('verify','reset'):
        link=_action_link(item.kind,item.recipient)
        content=account_email_content(item.kind,link)
    else:
        action=(item.content or {}).get('action','home_account_created')
        subject,title,body=COPY[action]
        path=('/#visit/'+item.content['bookingId']) if (item.content or {}).get('bookingId') else (
            '/#team' if action in ('callback_requested','helper_application_received','report_issue') else '/#visits')
        content=account_email_content('welcome',base+path,custom=(subject,title,body,'Open CookCredit Home',
            'This service message concerns your Home account or visit. Customer service: '+SUPPORT))
    # Keep the agreed existing authenticated sender. The shared transport sets
    # connectwithus as Reply-To; receiving address and sending credentials are
    # separate. No second mailbox credential or unverified From alias is needed.
    send_account_message(item.recipient,*content)
    return 'sent'
