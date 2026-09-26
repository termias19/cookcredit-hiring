"""Bound only hiring readiness; keep published learning and App Check intact."""
from hiring_capture_overlay import once

HELPERS = r'''
let hiringCheckSequence = 0;
function hiringReadinessError(error) {
  if (String(error?.code || '').startsWith('appCheck/')) {
    return 'Security check failed or is temporarily throttled. Try this application in Chrome, Edge or Safari. If it continues, contact CookCredit. [CC-HIRING-APPCHECK]';
  }
  return error?.code === 'hiring/readiness-timeout'
    ? 'The account security or application check did not finish within 20 seconds. Retry the check; if it continues, return to your application. [CC-HIRING-TIMEOUT]'
    : friendlyCloudError(error);
}
async function withHiringDeadline(operation) {
  let timer;
  try {
    return await Promise.race([Promise.resolve().then(operation), new Promise((_, reject) => {
      timer = setTimeout(() => reject(Object.assign(new Error('Hiring readiness timed out'),
        {code: 'hiring/readiness-timeout'})), 20000);
    })]);
  } finally { clearTimeout(timer); }
}
'''

VERIFY = r'''async function verifyHiringAccess() {
  if (!state.hiring || !cloudLibrary.user) return null;
  const sequence = ++hiringCheckSequence;
  const user = cloudLibrary.user;
  const context = state.hiring;
  const current = () => sequence === hiringCheckSequence && cloudLibrary.user === user && state.hiring === context;
  state.hiringSessionVerified = false;
  state.hiringVerificationError = '';
  syncHiringAuthState(user);
  try {
    const session = await withHiringDeadline(async () => {
      // Check security readiness explicitly, before allowing recording to start.
      await cloudLibrary.getAppCheckToken();
      if (!current()) return null;
      const idToken = await cloudLibrary.getIdToken();
      if (!current()) return null;
      return getHiringSession({context, idToken});
    });
    if (!current()) return null;
    if (session.status === 'processing' || session.status === 'completed') {
      $('hiring-auth-status').textContent = 'This attempt was already submitted. Returning to your application…';
      window.setTimeout(() => { if (current()) window.location.assign(context.returnUrl); }, 500);
      return session;
    }
    if (session.status !== 'started') throw new Error('This hiring assessment is no longer available. Return to your application to continue.');
    if (typeof renderHiringPresentation === 'function') renderHiringPresentation(session.presentation);
    state.hiringSessionVerified = true;
    syncHiringAuthState(user);
    return session;
  } catch (error) {
    if (!current()) return null;
    // Invalidate requests that finish after the deadline, including token refresh.
    hiringCheckSequence++;
    state.hiringVerificationError = hiringReadinessError(error);
    syncHiringAuthState(user);
    // Report a fixed code only: no token, email, URL or raw exception payload.
    void reportClientIssue('CC_HIRING_READINESS', 'hiring-auth',
      String(error?.code || '').startsWith('appCheck/') ? 'app-check-failed' :
        error?.code === 'hiring/readiness-timeout' ? 'readiness-timeout' : 'session-check-failed');
    throw error;
  }
}

'''

def apply_readiness(app):
    start=app.index('async function verifyHiringAccess()')
    end=app.index('function configureHiringResultActions()',start)
    app=once(app,app[start:end],HELPERS+'\n'+VERIFY)
    app=once(app,"  button.hidden = !!user && !state.hiringVerificationError;", """  const retry = $('btn-hiring-retry');
  if (retry) retry.hidden = !user || !state.hiringVerificationError;
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  button.hidden = !!user && !state.hiringVerificationError;""")
    anchor="  $('btn-submit-hiring').addEventListener('click', submitHiringResult);"
    app=once(app,anchor,"""  const retry = document.createElement('button');
  retry.id = 'btn-hiring-retry'; retry.type = 'button'; retry.textContent = 'Retry check';
  retry.className = $('btn-hiring-signin').className; retry.hidden = true;
  retry.addEventListener('click', () => { void verifyHiringAccess().catch(() => {}); });
  $('btn-hiring-signin').after(retry);
"""+anchor)
    start=app.index('async function configureHiringExperience(')
    end=app.index('function bindCloudLibrary()',start)
    block=app[start:end]
    updated=once(block,'await cloudLibrary.initialize();','await withHiringDeadline(() => cloudLibrary.initialize());')
    updated=once(updated,"$('hiring-auth-status').textContent = friendlyCloudError(error);", "$('hiring-auth-status').textContent = hiringReadinessError(error);")
    return once(app,block,updated)
