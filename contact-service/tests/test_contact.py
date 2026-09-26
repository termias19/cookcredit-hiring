from pathlib import Path
import sys,importlib.util,uuid,json
from unittest.mock import Mock
import pytest
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'backend/services'))
spec=importlib.util.spec_from_file_location('contact_app',repo/'contact-service/app.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Store:
 def __init__(self):self.data={};self.counts={}
 def ping(self):return True
 def get(self,k):return self.data.get(k)
 def set(self,k,v,nx=False,ex=None):
  if nx and k in self.data:return False
  self.data[k]=v;return True
 def eval(self,script,num,k,ttl):self.counts[k]=self.counts.get(k,0)+1;return self.counts[k]
@pytest.fixture
def setup(monkeypatch):
 store=Store();send=Mock();monkeypatch.setattr(module,'storage',lambda:store);monkeypatch.setattr(module,'send_google_smtp',send)
 return module.app.test_client(),store,send
def payload(**kwargs):return {'name':'Test','email':'test@example.com','message':'Hello <script>alert(1)</script>\nNext line','website':'','requestId':str(uuid.uuid4()),**kwargs}
def post(client,data,origin='https://cookcredit.com'):return client.post('/api/contact',json=data,headers={'Origin':origin})
def test_fixed_destination_and_escaped_content(setup):
 client,store,send=setup;data=payload();assert post(client,data).status_code==200
 recipient,subject,plain,markup=send.call_args.args
 assert recipient=='connectwithus@cookcredit.com' and subject=='CookCredit website contact'
 assert data['message'] in plain and '<script>' not in markup and '&lt;script&gt;' in markup
def test_duplicate_does_not_send_again(setup):
 client,store,send=setup;data=payload()
 assert post(client,data).status_code==200 and post(client,data).status_code==200
 send.assert_called_once()
 assert post(client,{**data,'message':'Changed'}).status_code==409
def test_pending_and_provider_failure_do_not_auto_retry(setup):
 client,store,send=setup;send.side_effect=RuntimeError('secret provider detail');data=payload()
 response=post(client,data);assert response.status_code==503 and b'secret provider detail' not in response.data
 assert post(client,data).status_code==409;send.assert_called_once()
@pytest.mark.parametrize('bad',[None,[],{},payload(email='x@a.com\nBcc: b@c.com'),payload(message=''),payload(message='x'*5001),payload(name=3),payload(website='spam'),payload(recipient='other@example.com'),payload(requestId='bad')])
def test_bad_input_does_not_send(setup,bad):
 client,store,send=setup;assert post(client,bad).status_code in (400,415);send.assert_not_called()
@pytest.mark.parametrize('origin',['https://evil.test','null','https://cookcredit.com.evil.test'])
def test_origin_rejected(setup,origin):
 client,store,send=setup;assert post(client,payload(),origin).status_code==403;send.assert_not_called()
def test_limits_and_storage_failure_are_closed(setup,monkeypatch):
 client,store,send=setup
 for _ in range(3):assert post(client,payload()).status_code==200
 assert post(client,payload()).status_code==429 and send.call_count==3
 monkeypatch.setattr(module,'storage',Mock(side_effect=RuntimeError('private redis details')))
 assert post(client,payload()).status_code==503 and send.call_count==3
def test_body_limit(setup):
 client,store,send=setup;assert post(client,payload(message='x'*25000)).status_code==413;send.assert_not_called()
def test_preflight(setup):
 client,_,send=setup;r=client.options('/api/contact',headers={'Origin':'https://cookcredit.com','Access-Control-Request-Method':'POST'})
 assert r.status_code==204 and r.headers['Access-Control-Allow-Origin']=='https://cookcredit.com'
 assert client.options('/api/contact',headers={'Origin':'https://evil.test'}).status_code==403
 send.assert_not_called()


def test_health_endpoint(setup):
 client,_,send=setup
 response=client.get('/api/health')
 assert response.status_code==200 and response.json=={'ok':True}
 send.assert_not_called()


def test_health_fails_closed_when_storage_is_unavailable(setup,monkeypatch):
 client,_,send=setup
 monkeypatch.setattr(module,'storage',Mock(side_effect=RuntimeError('private details')))
 response=client.get('/api/health')
 assert response.status_code==503 and response.json=={'ok':False}
 send.assert_not_called()
