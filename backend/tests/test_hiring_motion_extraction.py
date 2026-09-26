"""Real decoder/model tests are opt-in; no test touches applicant or cloud data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from scripts.extract_hiring_motion import extract, MODEL_SHA256
from scripts.inspect_hiring_video import VideoInspectionError
from tests.test_hiring_capture import claim


@pytest.fixture
def model():
    path=os.environ.get('HIRING_TEST_HAND_MODEL')
    if not path or not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('explicit offline model and decoder runtime required')
    pytest.importorskip('mediapipe');pytest.importorskip('cv2')
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==MODEL_SHA256
    return Path(path)


@pytest.fixture
def local_video(tmp_path,model):
    path=tmp_path/'blank.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=10',
                    '-t','1','-an','-c:v','mpeg4','-threads','1',str(path)],check=True,capture_output=True,timeout=20)
    c=claim();c.update(version=2,events=[],sourceWidth=320,sourceHeight=240,detectorWidth=320,
        durationMs=1000,countdownSec=0,samples=[[i*100,i*100,'Right'] for i in range(10)])
    return path,c


def test_independent_pixels_produce_no_score_for_blank_video(local_video,model):
    video,capture=local_video
    result=extract(video,capture,model)
    assert result['serverVerified'] is False
    assert result['recordingSha256']==hashlib.sha256(video.read_bytes()).hexdigest()
    assert result['replay']['metrics']['overall'] is None
    assert result['replay']['metrics']['strokes']==0
    assert result['replay']['missingSamples']==10
    assert result['maxNearestFrameDeltaMs']<1
    assert all(not row['wrists'] for row in result['observations'])


@pytest.mark.parametrize('damage',['geometry','detector-width','missing-events','capture-issue','timestamp-outside-video','model-hash'])
def test_extraction_rejects_unsupported_or_mismatched_evidence(local_video,model,tmp_path,damage):
    video,capture=local_video
    if damage=='geometry':capture['sourceWidth']=640
    elif damage=='detector-width':capture['detectorWidth']=480
    elif damage=='missing-events':capture['version']=1;capture.pop('events')
    elif damage=='capture-issue':capture['issues']=['camera-restarted']
    elif damage=='timestamp-outside-video':capture['durationMs']=5000;capture['samples']=[[4000,4000,'Right']]
    else:
        model=tmp_path/'wrong.task';model.write_bytes(b'not the published model')
    with pytest.raises(VideoInspectionError):extract(video,capture,model)


def test_extraction_honors_time_budget(local_video,model,monkeypatch):
    import scripts.extract_hiring_motion as module
    moments=iter([0,10])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(moments))
    with pytest.raises(VideoInspectionError,match='time budget'):
        extract(*local_video,model,budget_seconds=1)
