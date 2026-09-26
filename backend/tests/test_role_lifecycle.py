import os
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor
from models import RolePosting
from services.database import db_session
from tests.test_hiring_postgres import db, client, headers

pytestmark = pytest.mark.skipif(not os.environ.get("HIRING_TEST_DATABASE_URL"), reason="isolated PostgreSQL required")

def test_close_role_preserves_record_and_rejects_cross_company_and_viewer(client, db):
    path=f'/business/role/{db.role}/status'
    assert client.post(path,json={'status':'closed'}).status_code==401
    assert client.post(path,json={'status':'closed'},headers=headers('viewer')).status_code==403
    assert client.post(path,json={'status':'closed'},headers=headers('other')).status_code==404
    assert client.post(path,json={'status':'closed','orgId':str(db.other_org)},headers=headers('employer')).status_code==400
    for _ in range(2):
        response=client.post(path,json={'status':'closed'},headers=headers('employer'))
        assert response.status_code==200 and response.json['role']['status']=='closed'
    with db_session() as s:assert s.get(RolePosting,db.role).title=='Prep cook'
    response=client.get(f'/hiring/roles/{db.role}')
    assert response.status_code in (404,410),response.json

def test_reopening_uses_publication_quota_under_concurrency(client, db, monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED','0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED','1')
    ids=[]
    with db_session() as s:
        for i in range(3):s.add(RolePosting(org_id=db.org,title='Existing',status='open'))
        for i in range(3):
            rid=uuid.uuid4();ids.append(rid)
            s.add(RolePosting(id=rid,org_id=db.org,title='Closed',status='closed',requirements={'locationLabel':'Test city'}))
    def reopen(rid):
        with client.application.test_client() as c:
            return c.post(f'/business/role/{rid}/status',json={'status':'open'},headers=headers('employer')).status_code
    with ThreadPoolExecutor(max_workers=3) as p: statuses=list(p.map(reopen,ids))
    assert sorted(statuses)==[200,409,409]
    with db_session() as s:assert s.query(RolePosting).filter_by(org_id=db.org,status='open').count()==5

def test_integration_roles_and_incomplete_drafts_cannot_be_reopened(client,db):
    with db_session() as s:
        role=s.get(RolePosting,db.role);role.status='closed';role.integration_managed=True
    path=f'/business/role/{db.role}/status'
    assert client.post(path,json={'status':'open'},headers=headers('employer')).status_code==409
    with db_session() as s:s.get(RolePosting,db.role).integration_managed=False
    assert client.post(path,json={'status':'open'},headers=headers('employer')).status_code==400
