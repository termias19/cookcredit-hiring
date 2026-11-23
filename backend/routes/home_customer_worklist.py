"""Owner-only organization of existing Home requests; no messages or payments."""
from flask import Blueprint,jsonify,request,g
from extensions import limiter
from services import database,home_customer_worklist as worklist,home_customers as customers,home_visits as visits
from routes.home_visits import home_auth,is_owner,principal,json_body

worklist_bp=Blueprint('home_customer_worklist',__name__)


def owner():
    if not is_owner():visits.fail('forbidden','Only the Home owner can organize this customer list.',403)


@worklist_bp.post('/enrollments/search')
@home_auth
@limiter.limit('30 per minute',key_func=lambda:g.user_id)
def customer_search():
    owner()
    # Contact searches use a JSON body so names, email and phone terms do not
    # become URLs in browser history, referrers or Cloud request logs.
    with database.db_session()as session:
        result=worklist.search(session,json_body())
        customers.audit(session,principal(),'customer_worklist_viewed','directory')
    return jsonify(result)


@worklist_bp.post('/enrollments/<customer_id>/follow-up')
@home_auth
@limiter.limit('30 per minute',key_func=lambda:g.user_id)
def customer_followup(customer_id):
    owner();body=json_body();actor=principal()
    with database.db_session()as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'customer-followup:'+customer_id,body,
            lambda:worklist.save_followup(session,actor,customer_id,body))
    return jsonify(result)


@worklist_bp.post('/callbacks/<uuid:callback_id>/follow-up')
@home_auth
@limiter.limit('30 per minute',key_func=lambda:g.user_id)
def callback_followup(callback_id):
    owner();body=json_body();actor=principal()
    with database.db_session()as session:
        result=visits.command(session,actor,request.headers.get('Idempotency-Key'),'callback-followup:'+str(callback_id),body,
            lambda:worklist.callback_followup(session,actor,str(callback_id),body))
    return jsonify(result)
