const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const PRODUCTION_API_ORIGINS = Object.freeze([
  'https://api.cookcredit.com',
  'https://cookcredit-hiring-staging-915097816203.us-central1.run.app',
  'https://cookcredit-api-eqqoi6wp6a-uc.a.run.app',
]);

const DEVELOPMENT_API_ORIGINS = Object.freeze([
  'http://localhost:5000',
  'http://127.0.0.1:5000',
  'http://localhost:8791',
  'http://127.0.0.1:8791',
]);

const PRODUCTION_RETURN_ORIGINS = Object.freeze([
  'https://cookcredit.com',
  'https://www.cookcredit.com',
  'https://cookcredit-hiring-staging.web.app',
  'https://project-foodnlit.web.app',
  'https://foodnlit-1123e.web.app',
  'https://foodnlit-1123e.firebaseapp.com',
]);

const DEVELOPMENT_RETURN_ORIGINS = Object.freeze([
  'http://localhost:3000',
  'http://127.0.0.1:3000',
  'http://localhost:5173',
  'http://127.0.0.1:5173',
  'http://localhost:5202',
  'http://127.0.0.1:5202',
]);

const DEFAULT_API_ORIGINS = Object.freeze([
  ...PRODUCTION_API_ORIGINS,
  ...DEVELOPMENT_API_ORIGINS,
]);

const DEFAULT_RETURN_ORIGINS = Object.freeze([
  ...PRODUCTION_RETURN_ORIGINS,
  ...DEVELOPMENT_RETURN_ORIGINS,
]);

function bridgeError(message, code = 'hiring-link-invalid') {
  return Object.assign(new Error(message), { code });
}

function parseUrl(value, label) {
  try {
    return new URL(String(value || ''));
  } catch (_) {
    throw bridgeError(`The ${label} in this hiring link is invalid.`);
  }
}

function requireAllowedOrigin(value, label, allowedOrigins) {
  const parsed = parseUrl(value, label);
  if (parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') {
    throw bridgeError(`The ${label} in this hiring link is invalid.`);
  }
  if (!allowedOrigins.includes(parsed.origin)) {
    throw bridgeError(`This ${label} is not approved for CookCredit hiring.`);
  }
  return parsed.origin;
}

function requireReturnUrl(value, sessionId, allowedOrigins) {
  const parsed = parseUrl(value, 'return address');
  if (parsed.username || parsed.password || parsed.hash || parsed.search) {
    throw bridgeError('The return address in this hiring link is invalid.');
  }
  if (!allowedOrigins.includes(parsed.origin)) {
    throw bridgeError('This return address is not approved for CookCredit hiring.');
  }
  const expectedPath = `/application-assessment-return/${sessionId}`;
  if (parsed.pathname.replace(/\/$/, '') !== expectedPath) {
    throw bridgeError('The return address does not match this hiring assessment.');
  }
  return parsed.toString();
}

export function parseHiringContext(locationLike, options = {}) {
  const source = locationLike instanceof URL
    ? new URL(locationLike.toString())
    : new URL(locationLike?.href || String(locationLike));
  const sessionId = String(source.searchParams.get('hiringSession') || '').trim();
  if (!sessionId) return null;
  if (!SESSION_ID_PATTERN.test(sessionId)) {
    throw bridgeError('This CookCredit hiring assessment link is invalid.');
  }

  const apiOrigins = options.apiOrigins || DEFAULT_API_ORIGINS;
  const returnOrigins = options.returnOrigins || DEFAULT_RETURN_ORIGINS;
  const apiOrigin = requireAllowedOrigin(source.searchParams.get('apiOrigin'), 'API address', apiOrigins);
  const returnUrl = requireReturnUrl(source.searchParams.get('returnUrl'), sessionId, returnOrigins);

  return Object.freeze({ sessionId, apiOrigin, returnUrl, mode: 'test' });
}

export async function submitHiringAssessment({ context, assessmentId, originalLandmarks, idToken, appCheckToken, captureMetadata, fetchImpl = fetch }) {
  if (!context?.sessionId || !assessmentId || !idToken) {
    throw bridgeError('CookCredit cannot submit this assessment because required handoff data is missing.', 'hiring-submit-invalid');
  }
  const response = await fetchBounded(fetchImpl, 
    `${context.apiOrigin}/api/hiring/assessment-sessions/${encodeURIComponent(context.sessionId)}/complete`,
    {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
      headers: {
        Authorization: `Bearer ${idToken}`,
        'Content-Type': 'application/json',
        'X-Firebase-AppCheck': appCheckToken || '',
      },
      body: JSON.stringify({ assessmentId, ...(captureMetadata ? {captureMetadata} : {}), ...(originalLandmarks ? {originalLandmarks} : {}) }),
    },
  );

  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const message = typeof payload?.error === 'string' && payload.error.length <= 240
      ? payload.error
      : 'CookCredit could not attach this assessment to your application.';
    throw bridgeError(message, `hiring-submit-${response.status}`);
  }
  if (!['processing', 'completed'].includes(payload?.status)) {
    throw bridgeError('CookCredit received an unexpected hiring handoff response.', 'hiring-submit-response');
  }
  return payload;
}

export async function getHiringSession({ context, idToken, fetchImpl = fetch }) {
  if (!context?.sessionId || !idToken) {
    throw bridgeError('CookCredit cannot verify this hiring session.', 'hiring-session-invalid');
  }
  const response = await fetchBounded(fetchImpl, 
    `${context.apiOrigin}/api/hiring/assessment-sessions/${encodeURIComponent(context.sessionId)}`,
    {
      method: 'GET',
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
      headers: { Authorization: `Bearer ${idToken}` },
    },
  );
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const message = response.status === 404
      ? 'This assessment link does not belong to the signed-in CookCredit account.'
      : typeof payload?.error === 'string' && payload.error.length <= 240
        ? payload.error
        : 'CookCredit could not verify this hiring session.';
    throw bridgeError(message, `hiring-session-${response.status}`);
  }
  if (payload?.session?.sessionId !== context.sessionId || typeof payload.session.status !== 'string') {
    throw bridgeError('CookCredit received an unexpected hiring-session response.', 'hiring-session-response');
  }
  return payload.session;
}

export {
  DEFAULT_API_ORIGINS,
  DEFAULT_RETURN_ORIGINS,
  SESSION_ID_PATTERN,
};

async function fetchBounded(fetchImpl, url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);
  try { return await fetchImpl(url, {...options, signal: controller.signal}); }
  finally { clearTimeout(timer); }
}
