import pytest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from services.hiring_presentation import assessment_instructions, session_presentation, DEFAULT_INSTRUCTIONS
from models import RolePosting, Org, User

@pytest.mark.parametrize('value', [False, 12, [], {}, 'x' * 1501])
def test_rejects_invalid_instructions(value):
    with pytest.raises(ValueError): assessment_instructions(value)

def test_optional_instructions_are_plain_text():
    assert assessment_instructions(None) is None
    assert assessment_instructions('   ') is None
    assert assessment_instructions(' <script>alert(1)</script> ') == '<script>alert(1)</script>'

def test_context_follows_application_role_and_applicant():
    session = Mock()
    application = NS(id='application-a', role_posting_id='role-a', applicant_id='user-a', applicant_details=None)
    records = {(RolePosting, 'role-a'): NS(org_id='org-a', title='Prep cook', requirements={'assessmentInstructions':'Role instructions'}),
               (Org, 'org-a'): NS(name='Kitchen A', brand_logo_url='https://example.test/logo.png'),
               (User, 'user-a'): NS(name='Applicant A')}
    session.get.side_effect = lambda model, key: records[(model, key)]
    session.query.return_value.filter_by.return_value.first.return_value = None
    result = session_presentation(session, application)
    assert result == dict(companyName='Kitchen A', logoUrl='https://example.test/logo.png', roleTitle='Prep cook', instructions='Role instructions', applicantName='Applicant A')
    session.query.return_value.filter_by.assert_called_once_with(application_id='application-a')
    session.query.return_value.filter_by.return_value.first.return_value = NS(request_config={'assessmentInstructions':'Invitation instructions'})
    assert session_presentation(session, application)['instructions'] == 'Invitation instructions'
    session.query.return_value.filter_by.return_value.first.return_value = NS(request_config={})
    assert session_presentation(session, application)['instructions'] == DEFAULT_INSTRUCTIONS
