import json
from datetime import datetime,timedelta,timezone
from tests.test_webhook_recovery import delivery,db
from models import PartnerWebhookDelivery
from services import database,operations,partner_integrations


def test_exhausted_worker_alerts_even_when_later_batch_is_empty(delivery,capsys):
    with database.db_session() as session:
        row=session.get(PartnerWebhookDelivery,delivery[0]);row.attempts=partner_integrations.MAX_DELIVERY_ATTEMPTS
    stats=partner_integrations.dispatch_partner_webhooks(send=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Must not send')))
    assert stats['failed']==1
    assert not operations.report_queue_health('webhook')
    event=json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event['severity']=='ERROR' and event['failed']==1
    assert 'example.test' not in json.dumps(event) and 'secret' not in json.dumps(event)
    assert partner_integrations.dispatch_partner_webhooks()['claimed']==0
    assert not operations.report_queue_health('webhook')


def test_stale_pending_queue_is_observable(delivery,capsys):
    with database.db_session() as session:
        row=session.get(PartnerWebhookDelivery,delivery[0]);row.created_at=datetime.now(timezone.utc)-timedelta(minutes=11)
    assert not operations.report_queue_health('webhook')
    event=json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event['pending']==1 and event['oldestSeconds']>=660
