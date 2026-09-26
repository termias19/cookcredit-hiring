"""Add original replay samples only to the prepared hiring copy, not learning."""
from hiring_capture_overlay import once

def apply_original_landmarks(app, bridge):
    if 'originalLandmarks: hiringLandmarks.finish(),' not in app:
        app = once(app, '      assessmentId: state.cloudAssessmentId,',
                   '      assessmentId: state.cloudAssessmentId,\n      originalLandmarks: hiringLandmarks.finish(),')
    app = "import {createLandmarkCapture} from './landmark-capture.mjs';\nconst hiringLandmarks = createLandmarkCapture();\n" + app
    app = once(app, 'function setupRecorder() {', 'function setupRecorder() {\n  hiringLandmarks.start(null);')
    app = once(app, '    state.recorder.start();', '    state.recorder.start();\n    if (state.hiring) hiringLandmarks.start(state.video.currentTime);')
    app = once(app, 'function processFrame() {', 'function processFrame() {\n  const originalLandmarkTime = state.video.currentTime;')
    app = once(app, '  drawOverlay(knifeLm, otherLm);',
               "  if (state.hiring && state.recorder?.state === 'recording') hiringLandmarks.add(originalLandmarkTime, knifeLm, otherLm);\n  drawOverlay(knifeLm, otherLm);")
    bridge = once(bridge, 'assessmentId, idToken, appCheckToken, captureMetadata, fetchImpl = fetch',
                  'assessmentId, originalLandmarks, idToken, appCheckToken, captureMetadata, fetchImpl = fetch')
    bridge = once(bridge, 'JSON.stringify({ assessmentId, ...(captureMetadata ? {captureMetadata} : {}) })',
                  'JSON.stringify({ assessmentId, ...(captureMetadata ? {captureMetadata} : {}), ...(originalLandmarks ? {originalLandmarks} : {}) })')
    return app, bridge
