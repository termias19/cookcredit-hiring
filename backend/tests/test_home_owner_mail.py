"""Internal follow-up recipient is separate from the public sender/support."""
from types import SimpleNamespace
from services import home_mail


def test_operator_notices_use_only_configured_deduplicated_owners(monkeypatch):
    monkeypatch.setenv('HOME_OWNER_EMAILS',' Owner@example.test ,owner@example.test ')
    monkeypatch.setenv('HOME_OPERATOR_EMAILS','other-staff@example.test')
    for action in home_mail.OPERATOR_ACTIONS:
        assert home_mail._recipients(None,SimpleNamespace(action=action))==[('owner@example.test',None)]
    assert home_mail.SUPPORT=='connectwithus@cookcredit.com'


def test_unconfigured_development_owner_keeps_existing_support_fallback(monkeypatch):
    monkeypatch.delenv('HOME_OWNER_EMAILS',raising=False)
    assert home_mail._recipients(None,SimpleNamespace(action='callback_requested'))==[(home_mail.SUPPORT,None)]


def test_owner_alert_delivery_keeps_contact_details_private_and_links_to_callback_queue(monkeypatch):
    from services import account_email
    monkeypatch.setenv('HOME_PUBLIC_URL','https://home.example.test')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','production')
    monkeypatch.setenv('HOME_OWNER_EMAILS','owner@example.test')
    delivered=[]
    monkeypatch.setattr(account_email,'send_account_message',lambda *args:delivered.append(args))
    recipient,_=home_mail._recipients(None,SimpleNamespace(action='callback_requested'))[0]
    item=SimpleNamespace(recipient=recipient,user_id=None,kind='home_notice',content={'action':'callback_requested'})
    assert home_mail.deliver(item)=='sent'
    assert len(delivered)==1 and delivered[0][0]=='owner@example.test'
    assert 'https://home.example.test/#team' in delivered[0][2]
    assert home_mail.SUPPORT in delivered[0][2]
