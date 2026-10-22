/**
 * Mise API client.
 *
 * Thin endpoint wrappers over the shared HTTP client (utils/http.js), which
 * owns the base URL, auth header, and body/response handling.
 */

import { http } from './http'

export function resolveSearchLocation({ token, location }) {
  return http('/api/location/resolve', { method: 'POST', token, body: location, throwOnError: true })
}
export function getNearbyCooks({ token, locationToken, radiusMiles, page = 1 }) {
  return http('/api/cooks/nearby', { method: 'POST', token, body: { locationToken, radiusMiles, page }, throwOnError: true })
}
export function updateCookServiceArea({ token, location }) {
  return http('/api/cooks/me/service-area', { method: location ? 'PUT' : 'DELETE', token,
    body: location ? { ...location, accepted: true } : undefined, throwOnError: true })
}

export function getAssessmentSharing({ token, roleId, attemptId }) {
  return http(`/api/assessment-sharing/${encodeURIComponent(roleId)}/${encodeURIComponent(attemptId)}`, { token, throwOnError: true })
}

export function shareAssessment({ token, roleId, attemptId, consentVersion }) {
  return http(`/api/assessment-sharing/${encodeURIComponent(roleId)}/${encodeURIComponent(attemptId)}`, {
    method: 'POST', token, body: { accepted: true, consentVersion }, throwOnError: true,
  })
}

export function revokeAssessmentSharing({ token, shareId }) {
  return http(`/api/assessment-sharing/${encodeURIComponent(shareId)}/revoke`, { method: 'POST', token, throwOnError: true })
}

// ── Cook skill test ──────────────────────────────────────────────────────────
// Submit the captured chopping trajectory (+ optional clip) for SERVER-SIDE
// scoring. Never trust a client score; the backend recomputes it.
export async function submitSkillTest({ token, payload, videoBlob }) {
  const fd = new FormData()
  fd.append('payload', JSON.stringify(payload))          // { metadata, trajectory }
  if (videoBlob && videoBlob.size) fd.append('video', videoBlob, 'clip.webm')
  return http('/api/skills/submit', { method: 'POST', token, formData: fd, throwOnError: true })
}

export async function getSkillStatus(token) {
  return http('/api/skills/me', { token })
}

// One skill attempt (both scores + verification state) — polled after submit for the
// two-phase UI: PROVISIONAL -> VERIFYING -> VERIFIED | DISPUTED | INSUFFICIENT.
export async function getSkillAttempt({ token, id }) {
  return http(`/api/skills/${encodeURIComponent(id)}`, { token })
}

// ── Cook application ─────────────────────────────────────────────────────────
// Submit the cook application (bio + cuisines + rate) AFTER the skill test. The
// backend emails connectwithus@cookcredit.com and marks the cook 'pending' — it
// does NOT grant the cook role (that's manual team approval).
export async function submitCookApplication({ token, auth, application }) {
  return http('/api/cook-application', { method: 'POST', token, auth, body: application, throwOnError: true })
}

// Direct-to-Storage upload: ask the backend for a signed PUT URL, then upload the
// clip straight to the bucket (keeps the big file off the API workers). Throws if
// signing/CORS isn't configured -> caller falls back to the multipart path.
export async function getSkillUploadUrl({ token, contentType, sessionId }) {
  // session_id names the storage object, so a retry of the same capture
  // overwrites one blob instead of orphaning duplicates.
  return http('/api/skills/upload-url', {
    method: 'POST', token, body: { content_type: contentType, session_id: sessionId }, throwOnError: true,
  })
}

export async function putToSignedUrl(uploadUrl, blob, contentType) {
  // External signed URL (not our API) -> raw fetch, no auth header.
  const res = await fetch(uploadUrl, {
    method: 'PUT', headers: { 'Content-Type': contentType }, body: blob,
  })
  if (!res.ok) throw new Error(`direct upload failed (${res.status})`)
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export async function syncUser({ auth, name, phone, roles, activeRole }) {
  return http('/api/auth/sync', { method: 'POST', auth, body: { name, phone, roles, activeRole } })
}

export async function getMe({ auth }) {
  return http('/api/auth/me', { auth })
}

// ─── Cooks (public profile + cook self-view) ─────────────────────────────────
// Public, paginated list of discoverable cooks (approved + skill_verified) for Browse.
// Optional { city, cuisine, page, perPage }. No auth.
export async function getCooks({ city, cuisine, page = 1, perPage = 24 } = {}) {
  const qs = new URLSearchParams({ page, perPage })
  if (city) qs.set('city', city)
  if (cuisine) qs.set('cuisine', cuisine)
  return http(`/api/cooks?${qs.toString()}`)
}

// Public cook profile — no auth (route /cook/:id is unauthenticated). Returns the
// biometric-safe payload (name, photoUrl, skill credential, bio, cuisines, dishes).
export async function getCook(cookId) {
  return http(`/api/cooks/${encodeURIComponent(cookId)}`)
}
// The signed-in cook's own profile for the dashboard (incl. applicationStatus + stripeConnected).
export async function getCookMe({ auth }) {
  return http('/api/cooks/me', { auth })
}

// Self-edit the cook's descriptive profile (bio/cuisines/specialties/rate/radius/city/state/years/
// dietary). PATCH semantics — only the keys you pass change. The earned skill credential, Stripe,
// and approval state are NOT editable here (the server ignores/rejects them). Returns the fresh
// /api/cooks/me shape.
export async function updateCookProfile({ auth, token, ...fields }) {
  return http('/api/cooks/me', { method: 'PATCH', auth, token, body: fields, throwOnError: true })
}

export async function updateMe({ auth, ...updates }) {
  return http('/api/auth/me', { method: 'PATCH', auth, body: updates })
}

// ─── Beam (broadcast a craving) ───────────────────────────────────────────────
// An eater broadcasts a craving to qualifying cooks (city-wide first); cooks respond with a
// note + price; the eater reviews responders and picks one. Payment-agnostic (works in both the
// US/Stripe and ET/Addis markets). Backend: routes/beams.py.

// Optional craving photo — validated + EXIF-stripped server-side, stored under cravings/{uid}/.
export async function uploadCravingPhoto({ auth, file }) {
  const fd = new FormData()
  fd.append('file', file)
  return http('/api/beams/photo', { method: 'POST', auth, formData: fd, throwOnError: true })
}

export async function createBeam({ auth, cravingText, scope = 'citywide', city, photoUrl }) {
  return http('/api/beams', {
    method: 'POST', auth, body: { cravingText, scope, city, photoUrl }, throwOnError: true,
  })
}

// The signed-in eater's own beams, newest first (each with responseCount).
export async function getMyBeams({ auth, page = 1, perPage = 20 } = {}) {
  return http(`/api/beams/mine?page=${page}&perPage=${perPage}`, { auth })
}

// The signed-in cook's inbox of open beams in their city (recipient rows still 'pending').
export async function getBeamInbox({ auth, page = 1, perPage = 20 } = {}) {
  return http(`/api/beams/inbox?page=${page}&perPage=${perPage}`, { auth })
}

export async function getBeam({ auth, id }) {
  return http(`/api/beams/${encodeURIComponent(id)}`, { auth })
}

// Eater-owner only: responder cards to choose from.
/** Beam concierge chat turn. Returns {reply, draft|null}; the draft only
 *  prefills the composer — the human confirms, and POST /api/beams re-validates. */
export async function beamAgentChat({ auth, messages, city, lang }) {
  return http('/api/beams/agent', {
    method: 'POST', auth, body: { messages, city, lang }, timeoutMs: 60_000,
  })
}

export async function getBeamResponses({ auth, id }) {
  return http(`/api/beams/${encodeURIComponent(id)}/responses`, { auth })
}

// Cook: offer a note + price on a matched beam.
export async function respondToBeam({ auth, id, note, price }) {
  return http(`/api/beams/${encodeURIComponent(id)}/respond`, {
    method: 'POST', auth, body: { note, price }, throwOnError: true,
  })
}

// Eater-owner: pick a responder -> beam 'fulfilled'. An optional paymentMethod
// (cod | chapa | telebirr | cbe) creates the order in the same call (ET checkout). Omit it for a
// pure connect (backward-compatible).
export async function chooseResponder({ auth, beamId, responseId, paymentMethod }) {
  return http(`/api/beams/${encodeURIComponent(beamId)}/choose`, {
    method: 'POST', auth, body: { responseId, paymentMethod }, throwOnError: true,
  })
}

export async function cancelBeam({ auth, id }) {
  return http(`/api/beams/${encodeURIComponent(id)}/cancel`, { method: 'POST', auth, throwOnError: true })
}

// Cook: dismiss a beam from the inbox.
export async function declineBeam({ auth, id }) {
  return http(`/api/beams/${encodeURIComponent(id)}/decline`, { method: 'POST', auth, throwOnError: true })
}

// ─── Orders / payment (ET: Chapa + cash-on-delivery) ──────────────────────────
// An order is created when an eater picks a cook with a paymentMethod (see chooseResponder).
// Cash-on-delivery needs nothing further; online methods (telebirr / Chapa / CBE Birr) settle
// through Chapa. Backend: routes/orders.py.

// Initialize the online checkout for an order -> { order, checkoutUrl }. Redirect the eater there.
export async function payOrder({ auth, orderId }) {
  return http(`/api/orders/${encodeURIComponent(orderId)}/pay`, { method: 'POST', auth, throwOnError: true })
}

// Confirm payment by reference after the eater returns from Chapa -> { order, paid }.
export async function verifyOrder({ auth, orderId }) {
  return http(`/api/orders/${encodeURIComponent(orderId)}/verify`, { method: 'POST', auth, throwOnError: true })
}

// ─── Stripe Connect ─────────────────────────────────────────────────────────

export async function onboardCook({ auth }) {
  return http('/api/stripe/connect/onboard', { method: 'POST', auth })
}

export async function getConnectStatus({ auth }) {
  return http('/api/stripe/connect/status', { auth })
}

export async function getConnectDashboard({ auth }) {
  return http('/api/stripe/connect/dashboard', { method: 'POST', auth })
}

export async function getCookBalance({ auth }) {
  return http('/api/stripe/connect/balance', { auth })
}

// ─── Profile Image Upload ───────────────────────────────────────────────────

export async function uploadPortfolioImage({ auth, file }) {
  const fd = new FormData()
  fd.append('file', file)
  return http('/api/profile/upload-portfolio', { method: 'POST', auth, formData: fd })
}

// ─── Skill assessment (standalone graded product) ────────────────────────────
// Submit a captured wrist trajectory (+ optional clip URL) for SERVER-SIDE
// scoring + persistence. The backend recomputes the grade (never trust the
// client) and returns the authoritative result:
//   { id, kind, skillScore, tier, verified, result, videoUrl, createdAt,
//     assessmentNumber, isFirst }
export async function submitAssessment({ auth, token, metadata, trajectory, videoUrl }) {
  const body = { metadata, trajectory, ...(videoUrl ? { video_url: videoUrl } : {}) }
  return http('/api/assessments', { method: 'POST', auth, token, body, throwOnError: true })
}

// ─── Business / B2B workspace ────────────────────────────────────────────────
// All org-scoped; the backend checks org membership. activate grants the
// 'business' role + creates the org. The workspace store (BusinessContext) can
// call these and fall back to its local store when offline / not signed in.
export async function activateBusiness({ token, org }) {
  return http('/api/business/activate', { method: 'POST', token, body: org || {} })
}
export async function getBusinessOrg({ token }) {
  return http('/api/business/org', { token })
}
export async function getBusinessRoles({ token }) {
  return http('/api/business/roles', { token })
}
export async function createBusinessRole({ token, role }) {
  return http('/api/business/roles', { method: 'POST', token, body: role, throwOnError: true })
}
export async function updateBusinessRole({ token, id, role }) {
  return http(`/api/business/role/${id}`, { token, method: 'PATCH', body: role, throwOnError: true })
}
export async function changeBusinessRoleStatus({ token, id, status }) {
  return http(`/api/business/role/${id}/status`, { method: 'POST', token, body: { status }, throwOnError: true })
}
export async function getBusinessRole({ token, id }) {
  return http(`/api/business/role/${id}`, { token })
}
export async function moveBusinessStage({ token, id, cookId, stage }) {
  return http(`/api/business/role/${id}/stage`, { method: 'POST', token, body: { cookId, stage } })
}
export async function getBusinessCandidates({ token }) {
  return http('/api/business/candidates', { token })
}
export async function getBusinessShortlist({ token }) {
  return http('/api/business/shortlist', { token })
}
export async function toggleBusinessShortlist({ token, cookId }) {
  return http('/api/business/shortlist', { method: 'POST', token, body: { cookId } })
}
export async function setBusinessPlan({ token, plan }) {
  return http('/api/business/plan', { method: 'POST', token, body: { plan } })
}
export async function getBusinessBilling({ token }) {
  return http('/api/stripe/business/status', { token, throwOnError: true })
}
export async function createBusinessCheckout({ token, requestId, plan = 'team', interval = 'month', priceId }) {
  return http('/api/stripe/business/checkout', {
    method: 'POST', token, body: { requestId, plan, interval, priceId }, throwOnError: true,
  })
}
export async function createBusinessBillingPortal({ token }) {
  return http('/api/stripe/business/portal', { method: 'POST', token, throwOnError: true })
}
export async function updateBusinessIntegrations({ token, branding }) {
  return http('/api/business/integrations', {
    method: 'PATCH', token, body: branding, throwOnError: true,
  })
}

export async function uploadCompanyLogo({ token, file }) {
  const formData = new FormData()
  formData.append('logo', file)
  return http('/api/business/integrations/logo', { method: 'POST', token, formData, throwOnError: true })
}

export async function removeCompanyLogo({ token }) {
  return http('/api/business/integrations/logo', { method: 'DELETE', token, throwOnError: true })
}
export async function getBusinessTeam({ token }) {
  return http('/api/business/team', { token, throwOnError: true })
}
export async function changeBusinessMember({ token, memberId, seatRole, remove = false }) {
  return http(`/api/business/team/members/${encodeURIComponent(memberId)}`, {
    method: remove ? 'DELETE' : 'PATCH', token, ...(remove ? {} : { body: { seatRole } }), throwOnError: true,
  })
}
export async function getBusinessActivity({ token, before, action, actor }) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries({ before, action, actor })) if (value) params.set(key, value)
  return http(`/api/business/activity?${params}`, { token, throwOnError: true })
}
export async function inviteBusinessTeamMember({ token, email, seatRole }) {
  return http('/api/business/team/invitations', {
    method: 'POST', token, body: { email, seatRole }, throwOnError: true,
  })
}
export async function revokeBusinessTeamInvitation({ token, invitationId }) {
  return http(`/api/business/team/invitations/${encodeURIComponent(invitationId)}/revoke`, {
    method: 'POST', token, throwOnError: true,
  })
}
export async function acceptBusinessTeamInvitation({ token, invitationToken }) {
  return http('/api/business/team/invitations/accept', {
    method: 'POST', token, body: { token: invitationToken }, throwOnError: true,
  })
}
export async function getPartnerApiKeys({ token }) {
  return http('/api/partner/manage/api-keys', { token, throwOnError: true })
}
export async function createPartnerApiKey({ token, name, scopes, environment = 'live' }) {
  return http('/api/partner/manage/api-keys', {
    method: 'POST', token, body: { name, scopes, environment }, throwOnError: true,
  })
}
export async function revokePartnerApiKey({ token, keyId }) {
  return http(`/api/partner/manage/api-keys/${encodeURIComponent(keyId)}/revoke`, {
    method: 'POST', token, throwOnError: true,
  })
}
export async function getPartnerWebhooks({ token }) {
  return http('/api/partner/manage/webhooks', { token, throwOnError: true })
}
export async function createPartnerWebhook({ token, url, eventTypes, environment = 'live' }) {
  return http('/api/partner/manage/webhooks', {
    method: 'POST', token, body: { url, eventTypes, environment }, throwOnError: true,
  })
}
export async function setPartnerWebhookActive({ token, webhookId, active }) {
  return http(`/api/partner/manage/webhooks/${encodeURIComponent(webhookId)}`, {
    method: 'PATCH', token, body: { active }, throwOnError: true,
  })
}
export async function getPartnerWebhookDeliveries({ token }) {
  return http('/api/partner/manage/webhook-deliveries', { token, throwOnError: true })
}
export async function replayPartnerWebhookDelivery({ token, deliveryId }) {
  return http(`/api/partner/manage/webhook-deliveries/${encodeURIComponent(deliveryId)}/replay`, {
    method: 'POST', token, throwOnError: true,
  })
}
// Gated playback URL for a candidate's verified-skill capture (only cooks who applied to the org).
export async function getCandidateVideo({ token, cookId, roleId, attemptId, landmarks = false }) {
  const filters = new URLSearchParams()
  if (landmarks) filters.set('landmarks', '1')
  if (roleId) filters.set('roleId', roleId)
  if (attemptId) filters.set('attemptId', attemptId)
  const query = filters.size ? `?${filters}` : ''
  return http(`/api/business/candidate/${encodeURIComponent(cookId)}/video${query}`, { token, throwOnError: true })
}
export async function getCandidateReport({ token, cookId, roleId }) {
  const query = roleId ? `?roleId=${encodeURIComponent(roleId)}` : ''
  return http(`/api/business/candidate/${encodeURIComponent(cookId)}/report${query}`, { token, throwOnError: true })
}

// ── Hiring applications ─────────────────────────────────────────────────────
// The public role can be opened from a branded link without an account. Applying,
// reserving attempts, and reading results always use the signed-in applicant.
export async function getHiringRole({ roleId, invitationToken }) {
  const query = invitationToken ? `?invite=${encodeURIComponent(invitationToken)}` : ''
  return http(`/api/hiring/roles/${encodeURIComponent(roleId)}${query}`, { throwOnError: true })
}

export async function applyToHiringRole({ token, roleId, answers, location, consentVersion, invitationToken, fullName, cv }) {
  const application = { answers, location, acceptedEvidenceShare: true, consentVersion, invitationToken, fullName }
  const formData = cv ? new FormData() : undefined
  if (formData) { formData.append('application', JSON.stringify(application)); formData.append('cv', cv) }
  return http(`/api/hiring/roles/${encodeURIComponent(roleId)}/apply`, {
    method: 'POST', token,
    formData, body: formData ? undefined : application,
    throwOnError: true,
  })
}

export async function getMyHiringApplication({ token, roleId }) {
  return http(`/api/hiring/roles/${encodeURIComponent(roleId)}/my-application`, { token, throwOnError: true })
}

export async function getHiringApplication({ token, applicationId }) {
  return http(`/api/hiring/applications/${encodeURIComponent(applicationId)}`, { token, throwOnError: true })
}

export async function startHiringAttempt({ token, applicationId }) {
  return http(`/api/hiring/applications/${encodeURIComponent(applicationId)}/attempts/start`, {
    method: 'POST', token, throwOnError: true,
  })
}

export async function getHiringAssessmentSession({ token, sessionId }) {
  return http(`/api/hiring/assessment-sessions/${encodeURIComponent(sessionId)}`, { token, throwOnError: true })
}

export async function getHiringApplications({ token, roleId, status, city, outcome, cursor, limit = 40 }) {
  const query = new URLSearchParams({ limit: String(limit) })
  if (status) query.set('status', status)
  if (city) query.set('city', city)
  if (outcome) query.set('outcome', outcome)
  if (cursor) query.set('cursor', cursor)
  return http(`/api/hiring/roles/${encodeURIComponent(roleId)}/applications?${query}`, { token, throwOnError: true })
}


export async function withdrawHiringApplication({ token, applicationId }) {
  return http(`/api/hiring/applications/${encodeURIComponent(applicationId)}/withdraw`, {
    method: 'POST', token, throwOnError: true,
  })
}
export async function recordCandidateNotice({ token, roleId, cookId, qualifications, method }) {
  return http(`/api/business/role/${roleId}/notice`, { method: 'POST', token, body: { cookId, qualifications, method } })
}
export async function requestOptOut({ token, roleId, reason }) {
  return http('/api/business/opt-out', { method: 'POST', token, body: { roleId, reason } })
}

// ─── Resume scanner ──────────────────────────────────────────────────────────
// Server-accurate parse → canonical key-points. The /resume screen runs the
// client taxonomy pass for the instant preview and can call this to persist the
// authoritative parse for a signed-in cook.
export async function parseResume({ token, text, file }) {
  if (file) {
    const fd = new FormData()
    fd.append('file', file)
    return http('/api/resume/parse', { method: 'POST', token, formData: fd, throwOnError: true })
  }
  return http('/api/resume/parse', { method: 'POST', token, body: { text }, throwOnError: true })
}

// The signed-in user's assessment history, newest first (paginated).
export async function getAssessments({ auth, page = 1, perPage = 20 } = {}) {
  return http(`/api/assessments?page=${page}&perPage=${perPage}`, { auth })
}

// One assessment by id (owner only).
export async function getAssessment({ auth, id }) {
  return http(`/api/assessments/${encodeURIComponent(id)}`, { auth })
}

// ─── Admin: cook-application review queue ─────────────────────────────────────
// Gated server-side to the ADMIN_EMAILS allowlist (/me returns isAdmin for the UI).
export async function listCookApplications({ token, status = 'pending' }) {
  return http(`/api/admin/cook-applications?status=${encodeURIComponent(status)}`, { token })
}
export async function approveCook({ token, uid }) {
  return http(`/api/admin/cook-applications/${encodeURIComponent(uid)}/approve`,
    { method: 'POST', token, throwOnError: true })
}
export async function rejectCook({ token, uid, note }) {
  return http(`/api/admin/cook-applications/${encodeURIComponent(uid)}/reject`,
    { method: 'POST', token, body: { note }, throwOnError: true })
}

export async function updateBusinessOrg({ token, updates }) {
  return http('/api/business/org', { method: 'PATCH', token, body: updates, throwOnError: true })
}

export async function listMyHiringApplications({ token, cursor }) {
  const query = new URLSearchParams({ limit: '20' })
  if (cursor) query.set('cursor', cursor)
  return http(`/api/hiring/my-applications?${query}`, { token, throwOnError: true })
}

export async function downloadHiringCv({ token, applicationId }) {
  return http(`/api/hiring/applications/${encodeURIComponent(applicationId)}/cv`, {
    token, responseType: 'blob', throwOnError: true,
  })
}

export async function getEmployerCandidateApplications({ token, cookId, roleId }) {
  const query = roleId ? '?roleId=' + encodeURIComponent(roleId) : ''
  return http(`/api/hiring/candidates/${encodeURIComponent(cookId)}/applications${query}`, { token, throwOnError: true })
}
export async function saveEmployerReview({ token, applicationId, review }) {
  return http(`/api/hiring/applications/${encodeURIComponent(applicationId)}/review`, { token, method: 'POST', body: review, throwOnError: true })
}
