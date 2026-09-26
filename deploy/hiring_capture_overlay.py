"""Pure, fail-closed transformations of the existing hiring overlay only."""
from pathlib import Path


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Capture integration anchor changed: ' + old[:70])
    return text.replace(old, new, 1)


def apply_capture(app, bridge):
    app = "import {HiringCapture} from './hiring-capture.mjs';\n" + app
    app = once(app, 'function resetSession() {',
               "function resetSession() {\n  if (state.hiring) state.hiringCapture?.event('session-reset', performance.now(), state.knifeHand);")
    app = once(app, "  state.knifeHand = state.knifeHand === 'Right' ? 'Left' : 'Right';",
               "  state.knifeHand = state.knifeHand === 'Right' ? 'Left' : 'Right';\n  if (state.hiring) state.hiringCapture?.event('hand-change', performance.now(), state.knifeHand);")
    app = once(app, '  state.recordingSurface = createCompositeRecordingSurface({',
               '  state.recordingSurface = state.hiring ? null : createCompositeRecordingSurface({')
    app = once(app, '    state.recorder.start();', """    if (state.hiring) {
      const priorCapture = state.hiringCapture;
      state.hiringCapture = new HiringCapture({video: state.video, hand: state.knifeHand,
        countdownSec: state.countdownSec, detectorWidth: state.detW, now: performance.now()});
      if (priorCapture && !priorCapture.done) state.hiringCapture.issue('camera-restarted');
      const capture = state.hiringCapture;
      state.recorder.addEventListener('error', () => capture.issue('recorder-error'));
    }
    state.recorder.start();""")
    app = once(app, '    result = state.landmarker.detectForVideo(state.detCanvas, tsMs);',
               """    result = state.landmarker.detectForVideo(state.detCanvas, tsMs);
    if (state.hiring) state.hiringCapture?.sample({now, startedAt: state.startedAt,
      hand: state.knifeHand, video: state.video});""")
    app = once(app, '  state.recorder = null;\n  state.recChunks = [];',
               """  if (state.hiring) state.hiringCapture?.finish(performance.now(), !!blob?.size);
  state.recorder = null;
  state.recChunks = [];""")
    app = once(app, '      assessmentId: state.cloudAssessmentId,',
               '      assessmentId: state.cloudAssessmentId,\n      captureMetadata: state.hiringCapture?.snapshot(),')
    app = app.replace("'camera-only fallback'", "(state.hiring ? 'camera recording' : 'camera-only fallback')")
    bridge = once(bridge, 'assessmentId, idToken, appCheckToken, fetchImpl = fetch',
                  'assessmentId, idToken, appCheckToken, captureMetadata, fetchImpl = fetch')
    bridge = once(bridge, 'JSON.stringify({ assessmentId })',
                  'JSON.stringify({ assessmentId, ...(captureMetadata ? {captureMetadata} : {}) })')
    return app, bridge


def capture_module():
    return Path(__file__).with_name('hiring-capture.mjs').read_text(encoding='utf-8')
