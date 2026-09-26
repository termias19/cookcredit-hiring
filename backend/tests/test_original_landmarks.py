import copy
import gzip
import json
from types import SimpleNamespace
import pytest
from services import landmark_recording as m

def capture():
    return {'version':1,'timebase':'recording-ms','mirrored':False,
            'frames':[[0,[[0.2,0.5] for _ in range(21)],None],[100,None,None]]}

def test_original_data_is_bounded_and_retains_empty_tracking_frames():
    assert json.loads(m.validate_landmarks(capture())) == capture()
    assert m.validate_landmarks(None) is None
    for frames in ([[100,None,None],[0,None,None]], [[0,[[float('nan'),0]]*21,None]],
                   [[120001,None,None]], [[0,None,None]]*1901):
        value=capture(); value['frames']=frames
        with pytest.raises(ValueError): m.validate_landmarks(value)

def test_store_is_compressed_create_only_and_bound_to_recording(monkeypatch):
    seen={}
    class Blob:
        generation=77
        def upload_from_string(self,data,**kw): seen.update(data=data,kw=kw,metadata=self.metadata)
    blob=Blob()
    monkeypatch.setattr(m,'get_storage_bucket',lambda:SimpleNamespace(blob=lambda path: (seen.update(path=path) or blob)))
    raw=m.validate_landmarks(capture())
    ref=m.save_landmarks(raw,{'storagePath':'cookcredit-skill/users/u/assessments/a/recording.mp4','generation':'42'},'u')
    assert gzip.decompress(seen['data']) == raw
    assert seen['kw']['if_generation_match'] == 0
    assert ref['generation']=='77' and ref['recordingGeneration']=='42'
    assert seen['metadata']['ownerUid']=='u'

def test_foreign_or_replaced_recording_cannot_get_landmark_url(monkeypatch):
    monkeypatch.setattr(m,'get_storage_bucket',lambda: pytest.fail('No storage access for mismatched evidence'))
    ref={'path':'foreign','generation':'1','recordingGeneration':'42','sha256':'a'*64}
    with pytest.raises(ValueError): m.landmarks_url(ref,'own/recording.mp4','42')
    with pytest.raises(ValueError): m.landmarks_url(ref,'own/recording.mp4','43')
    assert m.landmarks_url(None,'own/recording.mp4','42') is None



def test_full_engine_capture_retains_knife_and_trail_and_rejects_corruption():
    value=capture(); value.update(version=2,renderer='a'*64)
    visual={'width':1280,'height':720,'bladeExtendK':3.2,'knifePresent':True,
            'knifeConf':0.91,'knifeWorker':True,'bladeTrail':[[100.5,200],[103,201]]}
    value['frames']=[row+[copy.deepcopy(visual)] for row in value['frames']]
    assert json.loads(m.validate_landmarks(value))==value
    for key,bad in [('width',0),('height',9000),('knifeConf',float('nan')),
                    ('knifePresent',1),('bladeExtendK',99),('bladeTrail',[[0,0]]*49)]:
        broken=copy.deepcopy(value);broken['frames'][0][3][key]=bad
        with pytest.raises(ValueError):m.validate_landmarks(broken)
    value['renderer']='https://untrusted.example/renderer.js'
    with pytest.raises(ValueError):m.validate_landmarks(value)
