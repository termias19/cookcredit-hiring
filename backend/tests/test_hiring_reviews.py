from types import SimpleNamespace
from datetime import datetime, timezone
import pytest
from services import hiring_reviews as r


def test_private_revision_cannot_change_published_applicant_projection():
    published=SimpleNamespace(id='1',event_type=r.EVENTS[1],actor_id='owner',created_at=datetime.now(timezone.utc),detail={'status':'shortlisted','message':'Hello','notes':'SECRET'})
    draft=SimpleNamespace(id='2',event_type=r.EVENTS[0],actor_id='owner',created_at=datetime.now(timezone.utc),detail={'status':'hired','message':'DRAFT','notes':'SECRET 2'})
    view=r.review_view([draft,published],public=True)
    assert view['status']=='shortlisted' and view['message']=='Hello'
    assert set(view)=={'status','message','updatedAt'}
    assert r.review_view([draft],public=True) is None
    assert r.review_view([draft,published])['notes']=='SECRET 2'

@pytest.mark.parametrize('patch',[{'status':[]},{'status':{}},{'status':'auto_hired'},{'publish':'true'},{'message':''},{'notes':'x'*5001},{'message':'x\x00'},{'extra':'field'},{'revision':123}])
def test_invalid_review_is_rejected(patch):
    with pytest.raises(ValueError):r.validate_review({'status':'reviewing','publish':True,'message':'Hello',**patch})
