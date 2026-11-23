"""Enrollment-only wording and secure continuation; fake sender/provider only."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from services import home_mail,account_email,firebase
from services import home_customers,home_visits


@pytest.fixture
def mailbox(monkeypatch):
    for key,value in {'HOME_PUBLIC_URL':'https://home.example.test','HOME_ENROLLMENT_ONLY':'1',
        'COOKCREDIT_PRODUCT':'home-services','COOKCREDIT_ENVIRONMENT':'production',
        'HOME_ACCEPTANCE_EMAILS':'customer@example.test'}.items():monkeypatch.setenv(key,value)
    identity=SimpleNamespace(email='customer@example.test',email_verified=True,disabled=False)
    provider=SimpleNamespace(get_user=lambda uid:identity,get_user_by_email=lambda email:identity)
    monkeypatch.setattr(firebase,'get_auth',lambda:provider)
    sent=[];monkeypatch.setattr(account_email,'send_account_message',lambda *args:sent.append(args))
    return identity,sent


def notice(action='home_account_created'):
    return SimpleNamespace(recipient='customer@example.test',user_id='customer',kind='home_notice',
        content={'action':action,'bookingId':None})


def test_public_welcome_reuses_one_delivery_with_enrollment_cta_and_no_booking_promise(mailbox):
    identity,sent=mailbox
    assert home_mail.deliver(notice())=='sent'and len(sent)==1
    recipient,subject,text,html=sent[0]
    assert recipient==identity.email and subject=='Your CookCredit Home account is ready'
    assert 'Enrollment is free.'in text and 'does not reserve a visit or authorize a payment'in text
    assert 'optional call'in text and 'Save my service needs: https://home.example.test/#enroll'in text
    assert 'https://home.example.test/#enroll'in html
    assert '/#visits'not in text and '/#visits'not in html
    assert 'review your helper'not in text and 'full quote'not in text


def test_full_private_staging_welcome_keeps_its_existing_copy_and_destination(mailbox,monkeypatch):
    identity,sent=mailbox
    monkeypatch.setenv('HOME_ENROLLMENT_ONLY','0');monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','staging')
    assert home_mail.deliver(notice())=='sent'
    assert home_mail.COPY['home_account_created'][2]in sent[0][2]
    assert 'https://home.example.test/#visits'in sent[0][2]


@pytest.mark.parametrize('kind',['verify','reset'])
@pytest.mark.parametrize('target',['enroll','help'])
def test_auth_messages_keep_branded_action_link_and_explicit_safe_home_return(mailbox,monkeypatch,kind,target):
    identity,sent=mailbox;identity.email_verified=kind!='verify'
    action='https://home.example.test/#account/action?mode='+('verifyEmail'if kind=='verify'else'resetPassword')+'&oobCode=synthetic-only'
    link=Mock(return_value=action);monkeypatch.setattr(account_email,'_action_link',link)
    item=SimpleNamespace(recipient=identity.email,user_id='customer',kind=kind,content={'homeReturn':target})
    assert home_mail.deliver(item)=='sent'
    link.assert_called_once_with(kind,identity.email)
    assert action+'&next='+target in sent[0][2]
    assert len(sent)==1


def test_public_scope_does_not_redirect_existing_operator_callback_notices(mailbox):
    identity,sent=mailbox
    assert home_mail.deliver(notice('callback_requested'))=='sent'
    assert 'https://home.example.test/#team'in sent[0][2]
    assert '/#enroll'not in sent[0][2]


@pytest.mark.parametrize('target',[None,'visits','request','payout','availability','helping',
    'visit/11111111-1111-4111-8111-111111111111'])
def test_old_default_booking_and_helper_continuations_recover_to_enrollment(mailbox,target):
    assert home_customers.return_route(target)=='enroll'


@pytest.mark.parametrize('target',['enroll','help','callback','team'])
def test_public_safe_email_destinations_are_preserved_without_granting_team_access(mailbox,target):
    assert home_customers.return_route(target)==target


@pytest.mark.parametrize('target',['https://unrelated.example','//unrelated.example','visits?next=https://unrelated.example',
    'visit/not-a-uuid',{'route':'enroll'}])
def test_public_mail_still_rejects_malformed_or_external_destinations(mailbox,target):
    with pytest.raises(home_visits.HomeError)as rejected:home_customers.return_route(target)
    assert rejected.value.code=='invalid_return'


def test_full_private_mode_keeps_existing_email_defaults_and_booking_continuations(mailbox,monkeypatch):
    monkeypatch.setenv('HOME_ENROLLMENT_ONLY','0')
    assert home_customers.return_route()=='visits'
    assert home_customers.return_route('request')=='request'
    assert home_customers.return_route('payout')=='payout'
