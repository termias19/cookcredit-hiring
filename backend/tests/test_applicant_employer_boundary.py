"""Applicants cannot become employers by verifying email or forging navigation."""
import pytest
from flask import Flask
from middleware import auth
from services import hiring_access
from routes import business
from routes.hiring_access import access_bp

@pytest.mark.parametrize('method,path', [
    ('GET','/api/business/org'), ('GET','/api/business/roles'),
    ('GET','/api/business/candidates'), ('GET','/api/business/shortlist'),
    ('GET','/api/business/candidate/other/video'),
    ('POST','/api/business/activate'), ('POST','/api/business/roles'),
    ('GET','/api/access/owner/requests'),
])
def test_verified_applicant_is_rejected_before_any_employer_data_access(monkeypatch, method, path):
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setattr(auth, '_verify_token', lambda _: {'uid':'candidate','email':'candidate@example.test','email_verified':True})
    monkeypatch.setattr(hiring_access, 'access_allowed', lambda *a, **kw: False)
    monkeypatch.setattr(business, 'db_session', lambda: pytest.fail('Employer data must not be read'))
    app=Flask(__name__);app.config.update(TESTING=True,RATELIMIT_ENABLED=False)
    app.register_blueprint(business.business_bp,url_prefix='/api/business')
    app.register_blueprint(access_bp,url_prefix='/api/access')
    response=app.test_client().open(path,method=method,headers={'Authorization':'Bearer candidate'},json={'roles':['business'],'activeRole':'business','orgId':'other-company'})
    assert response.status_code==403
    assert response.json['code']=='staging_access_denied'


@pytest.mark.parametrize('approved,verified,expected', [(False,True,False),(True,False,False),(True,True,True)])
def test_account_profile_reports_actual_employer_approval(monkeypatch, approved, verified, expected):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from routes import auth as auth_routes
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED','1')
    monkeypatch.setattr(auth,'_verify_token',lambda _: {'uid':'candidate','email':'candidate@example.test','email_verified':verified})
    monkeypatch.setattr(hiring_access,'access_allowed',lambda *a,**kw: approved)
    user=SimpleNamespace(to_dict=lambda: {'id':'candidate','roles':['eater']},eater_profile=None,cook_profile=None)
    @contextmanager
    def db(): yield SimpleNamespace(get=lambda *a: user)
    monkeypatch.setattr(auth_routes,'db_session',db)
    monkeypatch.setattr(auth_routes,'_grant_cook_if_approved',lambda _: None)
    app=Flask(__name__);app.config.update(TESTING=True,RATELIMIT_ENABLED=False)
    app.register_blueprint(auth_routes.auth_bp,url_prefix='/api/auth')
    result=app.test_client().get('/api/auth/me',headers={'Authorization':'Bearer candidate'})
    assert result.status_code==200
    assert result.json['employerAccessAllowed'] is expected
    assert result.json['roles']==['eater']


def test_same_origin_launch_retains_session_and_return_binding(monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    from routes.hiring import _launch_url
    monkeypatch.setenv('ASSESSMENT_SAME_ORIGIN_ENABLED','1')
    monkeypatch.setenv('FRONTEND_URL','https://cookcredit-hiring-staging.web.app')
    monkeypatch.setenv('PUBLIC_API_URL','https://api.example.test')
    result=urlsplit(_launch_url('session-id'))
    assert result.netloc=='cookcredit-hiring-staging.web.app'
    assert result.path=='/landing/assessment/'
    query=parse_qs(result.query)
    assert query['hiringSession']==['session-id']
    assert query['returnUrl']==['https://cookcredit-hiring-staging.web.app/application-assessment-return/session-id']
    assert set(query)=={'mode','hiringSession','apiOrigin','returnUrl'}
