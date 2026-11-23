"""Canonical external recovery reads; local fake provider and disposable SQL."""
import copy
from types import SimpleNamespace
from datetime import timedelta
from sqlalchemy import select,func
from models.home_service import HomeFinancialOperation as Op,HomeStripeEvent,HomeEvent
from services import database,home_payments as money,home_finance_worker as worker,home_stripe
from tests.test_home_payments import app,home_db,provider,completed,detail,fresh,change
from tests.test_home_quotes import post
from tests.test_home_security_acceptance import transfer_object,signed_transfer_event


def externally_adjusted(client,provider):
    row,payment_id,_=completed(client,provider)
    worker.dispatch_operations(provider)
    with database.db_session()as session:
        transfer=session.execute(select(Op).where(Op.payment_id==payment_id,Op.kind=='transfer')).scalar_one()
    assert signed_transfer_event(client,transfer_object(transfer))=={'accepted':True}
    assert worker.dispatch_events(provider)['processed']==1
    return row,payment_id,transfer


def canonical(transfer,*,full=True):
    value=transfer_object(transfer)
    value.update(object='transfer',reversed=full,
        amount_reversed=value['amount']if full else value['amount']//2)
    return value


def queue_refresh(client,row,**kwargs):
    result=post(client,f"/visits/{row['id']}/payment/refresh",{},**kwargs)
    assert result.status_code==202,result.json
    return result


def reader(provider,value,reads):
    def retrieve(identifier):
        # The worker releases its claim/eligibility transaction before I/O.
        assert database.engine.pool.checkedout()==0
        reads.append(identifier)
        return copy.deepcopy(value)
    provider.transfer_status=retrieve


def test_full_canonical_recovery_unblocks_resolution_without_automatic_compensation(app,provider):
    client=app.test_client();row,payment_id,transfer=externally_adjusted(client,provider)
    calls=list(provider.calls);reads=[];reader(provider,canonical(transfer),reads)
    queue_refresh(client,row,key='same-refresh-command')
    queue_refresh(client,row,key='same-refresh-command')
    assert worker.dispatch_events(provider)['processed']==2  # checkout + transfer read
    payment=detail(client,row)['payment']
    assert payment['helperTransferBalanceKnown']and payment['helperTransferredCents']==0
    assert payment['helperFunds']=='held_after_reversal'
    assert payment['transferReconciliation']=='full_reversal_verified'
    assert payment['externalTransferAdjustment']is True
    assert detail(client,row)['issueOpen']  # Operator must still decide the outcome.
    assert change(client,fresh(client,row),'resolve_issue',uid='owner').status_code==200
    resolved=detail(client,row)
    assert not resolved['issueOpen']and resolved['payment']['helperTransferredCents']==0
    assert signed_transfer_event(client,transfer_object(transfer))=={'accepted':True}
    assert worker.dispatch_events(provider)['processed']==1
    assert detail(client,row)['version']==resolved['version']and not detail(client,row)['issueOpen']
    queue_refresh(client,row)
    worker.dispatch_events(provider)
    assert worker.dispatch_operations(provider)['processed']==0
    assert reads==[transfer.provider_id]and provider.calls==calls
    with database.db_session()as session:
        evidence=session.execute(select(HomeEvent).where(HomeEvent.action=='helper_transfer_reconciled')).scalars().all()
        assert len(evidence)==1 and evidence[0].details['reversedCents']==transfer.payload['amountCents']
        assert session.execute(select(func.count(Op.id)).where(Op.payment_id==payment_id,Op.kind=='reverse')).scalar_one()==0


def test_partial_canonical_recovery_stays_held_and_never_invents_a_helper_balance(app,provider):
    client=app.test_client();row,payment_id,transfer=externally_adjusted(client,provider)
    calls=list(provider.calls);reads=[];reader(provider,canonical(transfer,full=False),reads)
    queue_refresh(client,row)
    assert worker.dispatch_events(provider)['processed']==2
    value=detail(client,row)
    assert value['issueOpen']and value['payment']['status']=='review_required'
    assert value['payment']['helperTransferredCents']is None
    assert value['payment']['transferReconciliation']=='required'
    result=change(client,fresh(client,row),'resolve_issue',uid='owner')
    assert result.status_code==409 and result.json['code']=='provider_reconciliation_required'
    assert worker.dispatch_operations(provider)['processed']==0 and provider.calls==calls
    with database.db_session()as session:
        assert session.execute(select(HomeEvent.id).where(HomeEvent.action=='helper_transfer_reconciled')).first()is None


def test_canonical_mismatches_retry_safely_without_resolving_or_moving_money(app,provider):
    client=app.test_client();row,payment_id,transfer=externally_adjusted(client,provider)
    calls=list(provider.calls);correct=canonical(transfer);reads=[]
    queue_refresh(client,row)
    bad_values=[{**correct,field:value}for field,value in [
        ('id','tr_other'),('livemode',True),('amount',True),('amount',correct['amount']-1),
        ('currency','eur'),('destination','acct_other'),('source_transaction','ch_other'),
        ('transfer_group','toque:other'),('object','charge'),('amount_reversed',True),
        ('amount_reversed',correct['amount']+1),('reversed',False)]]
    for field,value in [('cookcredit_product','toque'),('home_payment_id','other'),('home_operation_id','other')]:
        bad=copy.deepcopy(correct);bad['metadata'][field]=value;bad_values.append(bad)
    for value in bad_values:
        reader(provider,value,reads)
        assert worker.dispatch_events(provider)['deferred']==1
        with database.db_session()as session:
            inbox=session.execute(select(HomeStripeEvent).where(HomeStripeEvent.kind=='transfer.reconcile')).scalar_one()
            assert inbox.status=='retry'and inbox.last_error in ('transfer_binding_mismatch','transfer_reversal_state_mismatch')
            inbox.available_at=money.now()-timedelta(seconds=1)
            assert session.execute(select(HomeEvent.id).where(HomeEvent.action=='helper_transfer_reconciled')).first()is None
        assert detail(client,row)['payment']['helperTransferredCents']is None
    assert provider.calls==calls


def test_cancel_and_report_issue_do_not_queue_money_recovery_on_an_unknown_external_adjustment(app,provider):
    client=app.test_client();row,payment_id,transfer=externally_adjusted(client,provider)
    calls=list(provider.calls)
    with database.db_session()as session:
        booking,visit,payment=money.require_payment_access(session,{'uid':'owner'},row['id'],True,lock=True)
        before=session.execute(select(func.count(Op.id)).where(Op.payment_id==payment_id)).scalar_one()
        # Exercise both financial entry points, including the late-payment/
        # cancelled-visit worker caller, without fabricating a public transition.
        money.cancel_payment(session,booking,visit,payment)
        money.on_visit_change(session,booking,visit,'report_issue')
        assert payment.status=='review_required'and visit.issue_open
        assert session.execute(select(func.count(Op.id)).where(Op.payment_id==payment_id)).scalar_one()==before
        assert len(money.external_transfer_reviews(session,payment))==1
    assert worker.dispatch_operations(provider)['processed']==0 and provider.calls==calls


def test_pending_money_operations_cannot_bypass_external_review(app,provider):
    client=app.test_client();row,payment_id,transfer=externally_adjusted(client,provider)
    calls=list(provider.calls)
    with database.db_session()as session:
        payment=money.payment_for_visit(session,transfer.booking_id)
        money.operation(session,payment=payment,actor=money.SYSTEM,kind='reverse',suffix=transfer.provider_id,
            payload={'paymentId':str(payment.id),'transferId':transfer.provider_id,'amountCents':transfer.payload['amountCents']})
        money.operation(session,payment=payment,actor=money.SYSTEM,kind='refund_cancel',
            payload={'paymentId':str(payment.id),'paymentIntentId':payment.payment_intent_id,'amountCents':1})
    assert worker.dispatch_operations(provider)['deferred']==2 and provider.calls==calls
    assert detail(client,row)['payment']['helperTransferBalanceKnown']is False


def test_transfer_status_adapter_is_only_a_read_on_the_existing_client(monkeypatch):
    reads=[]
    monkeypatch.setattr(home_stripe,'client',lambda:SimpleNamespace(transfers=SimpleNamespace(
        retrieve=lambda transfer_id:reads.append(transfer_id)or{'id':transfer_id})))
    assert home_stripe.StripeHome().transfer_status('tr_synthetic')=={'id':'tr_synthetic'}
    assert reads==['tr_synthetic']
