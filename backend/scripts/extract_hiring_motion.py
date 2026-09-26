"""Offline independent video extraction for published capture replay.

Run as a resource-limited subprocess. This diagnostic never changes an attempt,
contacts cloud services, reads browser wrist trajectories, or certifies a score.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.inspect_hiring_video import inspect_video, VideoInspectionError, MAX_BYTES
from services.hiring_capture import validate_capture
from services.published_capture_replay import replay_capture

MODEL_SHA256 = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'
RUNTIME = {'mediapipe': '0.10.32', 'opencv': '4.13.0'}


def extract(video, capture, model, *, budget_seconds=120):
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
    from mediapipe.tasks.python.core.base_options import BaseOptions
    if mp.__version__ != RUNTIME['mediapipe'] or cv2.__version__ != RUNTIME['opencv']:
        raise VideoInspectionError('Extraction runtime differs from the pinned diagnostic runtime')
    if not 1 <= budget_seconds <= 180:
        raise ValueError('Unsupported extraction budget')
    claim = validate_capture(capture)
    if claim is None or claim['version'] != 2 or not claim['samples'] or claim['issues']:
        raise VideoInspectionError('A complete version 2 capture is required')
    if claim['detectorWidth'] != 320:
        raise VideoInspectionError('Capture does not use the published detector geometry')
    model_bytes = Path(model).read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != MODEL_SHA256:
        raise VideoInspectionError('Published hand model hash mismatch')
    video = Path(video)
    if video.suffix.lower() not in ('.mp4','.mov','.webm'):
        raise VideoInspectionError('Unsupported local video extension')
    with video.open('rb') as source:
        data = source.read(MAX_BYTES+1)
    if not 0 < len(data) <= MAX_BYTES:
        raise VideoInspectionError('Recording exceeds the supported size')
    cv2.setNumThreads(1)
    deadline = time.monotonic()+budget_seconds
    with tempfile.TemporaryDirectory(prefix='hiring-motion-') as directory:
        directory = Path(directory)
        pinned_video = directory/('recording'+video.suffix.lower())
        pinned_model = directory/'hand_landmarker.task'
        pinned_video.write_bytes(data); pinned_model.write_bytes(model_bytes)
        preflight = inspect_video(pinned_video, claim)
        if preflight['issues']:
            raise VideoInspectionError('Recording geometry does not match the capture')
        width, height = preflight['width'], preflight['height']
        decoder = cv2.VideoCapture(str(pinned_video))
        observations, alignment = [], []
        previous_pts = -1.0
        decoded = 0
        def frame():
            nonlocal previous_pts, decoded
            if time.monotonic() >= deadline:
                raise VideoInspectionError('Independent extraction exceeded its time budget')
            ok, pixels = decoder.read()
            if not ok:
                return None
            decoded += 1
            pts = decoder.get(cv2.CAP_PROP_POS_MSEC)
            if (decoded > 21600 or not math.isfinite(pts) or pts < 0 or
                    pts <= previous_pts or pixels.shape[:2] != (height,width)):
                raise VideoInspectionError('Decoded frame geometry, count or timestamp is unsupported')
            previous_pts = pts
            return pts,pixels
        options = HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(pinned_model)),
            running_mode=RunningMode.VIDEO, num_hands=2, min_hand_detection_confidence=.5,
            min_hand_presence_confidence=.5, min_tracking_confidence=.5)
        try:
            if not decoder.isOpened():
                raise VideoInspectionError('Independent decoder could not open the recording')
            with HandLandmarker.create_from_options(options) as detector:
                left = frame(); right = frame()
                for offset, _, _ in claim['samples']:
                    while right is not None and right[0] < offset:
                        left,right = right,frame()
                    choices = [item for item in (left,right) if item is not None]
                    if not choices:
                        raise VideoInspectionError('No video frame covers capture timing')
                    chosen = min(choices,key=lambda item:abs(item[0]-offset))
                    delta = chosen[0]-offset
                    # This is a missing-media bound, not a calibrated score tolerance.
                    if abs(delta)>100:
                        raise VideoInspectionError('Capture timing is outside recorded video coverage')
                    small=cv2.resize(chosen[1],(320,max(1,math.floor(320*height/width+.5))),interpolation=cv2.INTER_LINEAR)
                    image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(small,cv2.COLOR_BGR2RGB))
                    result=detector.detect_for_video(image,offset)
                    observations.append({'offsetMs':offset,
                        'wrists':[[hand[0].x,hand[0].y] for hand in result.hand_landmarks],
                        'labels':[row[0].category_name if row else '' for row in result.handedness]})
                    alignment.append(delta)
        finally:
            decoder.release()
    replay = replay_capture(claim,observations)
    return {'schema':'independent-motion-extraction-v1','serverVerified':False,
        'scope':'Video-derived diagnostic; camera clock and browser/runtime calibration are not certified',
        'recordingSha256':preflight['sha256'],'modelSha256':MODEL_SHA256,'runtime':RUNTIME,
        'captureSha256':hashlib.sha256(json.dumps(claim,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'decoderFramesRead':decoded,'maxNearestFrameDeltaMs':max(map(abs,alignment)),
        'meanNearestFrameDeltaMs':sum(map(abs,alignment))/len(alignment),
        'replay':replay,'observations':observations}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=extract(args.video,json.loads(args.capture.read_text()),args.model)
    args.output.write_text(json.dumps(result,indent=2))
    print('Independent extraction completed. No applicant changes; serverVerified=false.')
