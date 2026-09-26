/**
 * In-memory employer workspace used only by the VITE_PREVIEW development build.
 *
 * The production API remains the source of truth. This adapter gives the local product tour
 * realistic, mutable responses so every employer screen can be exercised without Firebase,
 * Postgres, Stripe, or partner credentials.
 */
import { CANDIDATES, ORG, PIPELINE_SEED, ROLES_SEED } from './businessMock'

const now = new Date()
const inSevenDays = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString()

let org = {
  ...ORG,
  name: 'Juniper Hospitality Group',
  city: 'Atlanta, GA',
  plan: 'enterprise',
  seatRole: 'admin',
  branding: { logoUrl: null, color: '#1F6F5C' },
  embed: { key: 'embed_preview_6F2C', allowedOrigins: ['https://careers.juniper.example'] },
}

let roles = ROLES_SEED.map(role => role.id === 'r2' ? {
  ...role,
  title: 'Prep cook — restaurant kitchen',
  status: 'open',
  description: 'Prepare ingredients for restaurant service, keep cuts consistent, and maintain a safe, organized prep station.',
  location: { label: 'Atlanta, GA', city: 'Atlanta', state: 'GA' },
  employment: { type: 'Part time', shifts: ['Mon–Fri', '2–7 PM'], payMin: 24, payMax: 31, tips: true },
  attemptLimit: 3,
  questions: [
    { id: 'availability', label: 'Which shifts can you work?', type: 'multiselect', required: true, options: ['Weekday mornings', 'Weekday evenings', 'Weekends'] },
    { id: 'allergy', label: 'Have you cooked for guests with documented allergies?', type: 'yes_no', required: true, options: [] },
    { id: 'station', label: 'Tell us about your most recent prep-cook role.', type: 'long_text', required: false, options: [] },
  ],
  consentVersion: 'preview-2026-09',
  consentText: 'I choose to share my answers, approximate location, attempt history, each submitted assessment result, and temporary access to its recording with Juniper Hospitality Group. I can withdraw future access in CookCredit.',
} : role)

const assessment = (score, attemptId = `attempt-${score}`) => ({
  attemptId, status: 'review-required', score: null, tier: null, profileId: 'wrist_motion',
  profileVersion: 'knife-motion-v1',
  recordedAt: new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  deviceEstimates: { overall: score, rhythm: score, consistency: Math.max(0, score - 5), form: Math.max(0, score - 3), strokes: 28, cadence: 1.4, serverVerified: false, source: 'published-browser-assessment', zeroMayMeanUnavailable: true },
  outcome: {
    outcome: 'review_required', reasonCodes: ['live_assessment_manual_review'],
    explanation: 'Rhythm, consistency and form are browser estimates. Review the recording; independent score verification is not performed.',
    profile: { id: 'wrist_motion', version: 'knife-motion-v1', label: 'Knife work: rhythm, consistency and form', criteria: { minimumRhythm: 70, minimumConsistency: 70, minimumForm: 70 } },
    workflowGate: { status: 'human_review_required', automaticAdvancementEligible: false, automaticRejectionEligible: false, employmentValidated: false, humanDecisionRequired: true },
  },
  measurements: { rhythm: null, consistency: null, form: null },
  calculation: {
    scoreSource: 'Published live assessment; not independently verified', clientScoreUsedForHiring: false,
    comparison: 'Rhythm measures timing steadiness; consistency measures stroke-depth steadiness; form measures vertical motion. Available axes use weights 45%, 30% and 25%.',
    resultReason: 'These estimates do not certify knife skill, cut quality or food safety.',
  },
  provenance: { recordingGenerationPinned: true, profileId: 'wrist_motion', scoringSchema: 'published-wrist-motion-v1', attemptEventsPreserved: true },
  limitations: { employmentValidated: false, automaticHiringDecision: false,
    message: 'Review the recording. Browser estimates are not server-verified and cannot automatically advance or reject this applicant. A zero may indicate unavailable signal in the saved assessment.' },
})

const application = (id, candidateId, status, attemptsCompleted, score = null) => {
  const person = CANDIDATES.find(candidate => candidate.id === candidateId)
  const best = score == null ? null : assessment(score, `${id}-attempt-${attemptsCompleted}`)
  return {
    id,
    roleId: 'r2',
    status,
    submittedAt: new Date(now.getTime() - attemptsCompleted * 24 * 60 * 60 * 1000).toISOString(),
    candidate: { id: person.id, name: person.name },
    location: { city: person.city },
    answers: { availability: ['Weekday evenings'], allergy: true },
    attemptLimit: 3,
    attemptsCompleted,
    attemptsRemaining: 3 - attemptsCompleted,
    attempts: Array.from({ length: attemptsCompleted }, (_, index) => ({ slot: index + 1, status: 'completed' })),
    bestAssessment: null,
    latestAssessment: best,
  }
}

let shortlist = ['c1']
let applications = [
  application('app-amara', 'c1', 'ready', 2, 93),
  application('app-sara', 'c4', 'ready', 3, 84),
  application('app-mei', 'c3', 'assessment_processing', 1),
]
let myApplication = null
let invitations = [{ id: 'invite-1', email: 'kitchenlead@juniper.example', seatRole: 'hiring_manager', status: 'pending', expiresAt: inSevenDays }]
let apiKeys = [{ id: 'key-1', name: 'Production ATS', prefix: 'cc_live_7d2a', environment: 'live', scopes: ['assessments:read', 'assessments:write'], createdAt: now.toISOString(), revokedAt: null }]
let webhooks = [{ id: 'hook-1', url: 'https://ats.juniper.example/cookcredit-events', eventTypes: ['assessment.processing', 'assessment.evidence_ready'], active: true, failureCount: 0 }]
let deliveries = [
  { id: 'delivery-1', webhookId: 'hook-1', eventId: 'evt-evidence-1042', eventType: 'assessment.evidence_ready', status: 'delivered', attempts: 1, deliveredAt: now.toISOString(), lastError: null, createdAt: now.toISOString() },
  { id: 'delivery-2', webhookId: 'hook-1', eventId: 'evt-processing-1042', eventType: 'assessment.processing', status: 'pending', attempts: 2, deliveredAt: null, lastError: 'HTTP 503', createdAt: now.toISOString() },
]

function candidateReport(candidateId, roleId) {
  const candidate = CANDIDATES.find(item => item.id === candidateId) || CANDIDATES[0]
  const score = candidate.browserEstimate ?? 88
  const chosenRole = roles.find(item => item.id === roleId) || roles.find(item => item.id === 'r2')
  const current = assessment(score, `${candidate.id}-shared-attempt`)
  return {
    candidate,
    role: chosenRole ? { id: chosenRole.id, title: chosenRole.title } : null,
    assessment: current,
    attemptHistory: [current, { ...assessment(Math.max(60, score - 7), `${candidate.id}-earlier-attempt`), recordedAt: new Date(now.getTime() - 12 * 24 * 60 * 60 * 1000).toISOString() }],
    match: roleId ? {
      band: 'Review', total: null,
      gates: { passed: true, failures: [] },
      requirements: [
        { id: 'knife_skills', kind: 'required', status: 'review', source: 'review recording' },
        { id: 'high_volume_prep', kind: 'required', status: candidate.resumePoints.includes('high_volume_prep') ? 'met' : 'review', source: 'résumé' },
        { id: 'allergen_handling', kind: 'preferred', status: candidate.resumePoints.includes('allergen_handling') ? 'met' : 'review', source: 'résumé' },
      ],
    } : null,
    reviewPolicy: { humanDecisionRequired: true, scoreOnlyRejectionAllowed: false, alternativeAssessmentAvailable: true, candidateCanRevokeFutureEvidenceAccess: true },
  }
}

function rolePublic(role) {
  return {
    ...role,
    company: { name: org.name, city: org.city, logoUrl: org.branding.logoUrl, brandColor: org.branding.color },
    location: role.location || { label: org.city },
    employment: role.employment || { type: 'Role', shifts: [], payMin: null, payMax: null, tips: false },
    attemptLimit: role.attemptLimit || 3,
    questions: role.questions || [],
    consentVersion: role.consentVersion || 'preview-2026-09',
    consentText: role.consentText || 'I choose to share this application and assessment evidence with the employer.',
  }
}

const ok = data => ({ handled: true, data })

export async function previewBusinessRequest(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase()
  const url = new URL(path, 'http://preview.local')
  const pathname = url.pathname
  const body = opts.body || {}

  if (pathname === '/api/business/integrations/logo' && method === 'POST') {
    const file = opts.formData?.get('logo')
    if (!file) throw new Error('Choose a logo image.')
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
    org = { ...org, branding: { ...org.branding, logoUrl: dataUrl } }
    return ok({ org })
  }
  if (pathname === '/api/business/integrations/logo' && method === 'DELETE') {
    org = { ...org, branding: { ...org.branding, logoUrl: null } }
    return ok({ org })
  }

  if (pathname === '/api/business/org' && method === 'PATCH') { org = { ...org, ...body }; return ok({ org }) }
  if (pathname === '/api/business/org' && method === 'GET') return ok({ org })
  if (pathname === '/api/business/roles' && method === 'GET') return ok({ roles })
  if (pathname === '/api/business/roles' && method === 'POST') {
    const created = { ...body, id: `r-preview-${Date.now()}`, status: body.status || 'draft' }
    roles = [created, ...roles]
    return ok({ role: created })
  }
  if (pathname === '/api/business/candidates' && method === 'GET') return ok({
    candidates: CANDIDATES,
    scope: 'active-applicant-consent',
    screeningPolicy: { assessmentEmploymentValidated: false, automaticRankingEnabled: false, humanDecisionRequired: true, scoreOnlyRejectionAllowed: false },
  })
  if (pathname === '/api/business/shortlist' && method === 'GET') return ok({ cookIds: shortlist })
  if (pathname === '/api/business/shortlist' && method === 'POST') {
    shortlist = shortlist.includes(body.cookId) ? shortlist.filter(id => id !== body.cookId) : [...shortlist, body.cookId]
    return ok({ ok: true, shortlisted: shortlist.includes(body.cookId) })
  }

  let match = pathname.match(/^\/api\/business\/role\/([^/]+)$/)
  if (match && method === 'GET') {
    const role = roles.find(item => item.id === decodeURIComponent(match[1])) || null
    const pipeline = PIPELINE_SEED.filter(card => card.roleId === role?.id).map(card => ({ ...card, match: { band: 'Review', gates: { passed: true, failures: [] } } }))
    return ok({ role, pipeline })
  }
  match = pathname.match(/^\/api\/business\/role\/([^/]+)\/stage$/)
  if (match && method === 'POST') return ok({ ok: true, stage: body.stage })

  match = pathname.match(/^\/api\/business\/candidate\/([^/]+)\/report$/)
  if (match && method === 'GET') return ok(candidateReport(decodeURIComponent(match[1]), url.searchParams.get('roleId')))
  match = pathname.match(/^\/api\/business\/candidate\/([^/]+)\/video$/)
  if (match && method === 'GET') return ok({ videoUrl: '/landing/hero-loop.mp4', attemptId: `${decodeURIComponent(match[1])}-shared-attempt`, expiresInSeconds: 300 })

  if (pathname === '/api/stripe/business/status' && method === 'GET') return ok({ plan: org.plan, status: 'active', cancelAtPeriodEnd: false, periodEnd: null, hasCustomer: true, checkoutConfigured: true, integrationCheckoutConfigured: true, teamPrice: '$99', integrationPrice: '$299', integrationUsage: { periodStart: new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10), used: 147, limit: 1000, remaining: 853 } })
  if (pathname === '/api/stripe/business/checkout' && method === 'POST') return ok({ checkoutUrl: `${window.location.origin}/business/billing?checkout=success` })
  if (pathname === '/api/stripe/business/portal' && method === 'POST') return ok({ portalUrl: `${window.location.origin}/business/billing` })

  if (pathname === '/api/business/integrations' && method === 'PATCH') {
    org = { ...org, branding: { logoUrl: body.logoUrl || null, color: body.color || '#1F6F5C' }, embed: { ...org.embed, allowedOrigins: body.allowedOrigins || [] } }
    return ok({ org })
  }
  if (pathname === '/api/business/team' && method === 'GET') return ok({
    members: [
      { id: 'member-1', userId: 'preview-user', email: 'owner@juniper.example', name: 'Ermias', seatRole: 'admin', joinedAt: now.toISOString() },
      { id: 'member-2', userId: 'chef-lead', email: 'cheflead@juniper.example', name: 'Maya Chen', seatRole: 'recruiter', joinedAt: now.toISOString() },
    ],
    invitations,
    canManage: true,
  })
  if (pathname === '/api/business/team/invitations' && method === 'POST') {
    const invitation = { id: `invite-${Date.now()}`, email: body.email, seatRole: body.seatRole, status: 'pending', expiresAt: inSevenDays, inviteUrl: `${window.location.origin}/business/invite/preview-token`, emailDelivered: false }
    invitations = [invitation, ...invitations]
    return ok({ invitation })
  }
  match = pathname.match(/^\/api\/business\/team\/invitations\/([^/]+)\/revoke$/)
  if (match && method === 'POST') {
    invitations = invitations.map(item => item.id === decodeURIComponent(match[1]) ? { ...item, status: 'revoked' } : item)
    return ok({ ok: true })
  }

  if (pathname === '/api/partner/manage/api-keys' && method === 'GET') return ok({ keys: apiKeys })
  if (pathname === '/api/partner/manage/api-keys' && method === 'POST') {
    const key = { id: `key-${Date.now()}`, name: body.name, prefix: 'cc_live_preview', environment: body.environment || 'live', scopes: body.scopes || [], secret: 'cc_live_preview_only_shown_once', createdAt: now.toISOString(), revokedAt: null }
    apiKeys = [key, ...apiKeys]
    return ok({ key })
  }
  match = pathname.match(/^\/api\/partner\/manage\/api-keys\/([^/]+)\/revoke$/)
  if (match && method === 'POST') {
    const id = decodeURIComponent(match[1])
    apiKeys = apiKeys.map(item => item.id === id ? { ...item, revokedAt: now.toISOString() } : item)
    return ok({ key: apiKeys.find(item => item.id === id) })
  }
  if (pathname === '/api/partner/manage/webhooks' && method === 'GET') return ok({ webhooks })
  if (pathname === '/api/partner/manage/webhooks' && method === 'POST') {
    const webhook = { id: `hook-${Date.now()}`, url: body.url, environment: body.environment || 'live', eventTypes: body.eventTypes || [], active: true, failureCount: 0, secret: 'whsec_preview_only_shown_once' }
    webhooks = [webhook, ...webhooks]
    return ok({ webhook })
  }
  if (pathname === '/api/partner/manage/webhook-deliveries' && method === 'GET') return ok({ deliveries })
  match = pathname.match(/^\/api\/partner\/manage\/webhook-deliveries\/([^/]+)\/replay$/)
  if (match && method === 'POST') {
    const id = decodeURIComponent(match[1])
    deliveries = deliveries.map(item => item.id === id ? { ...item, status: 'pending', attempts: 0, deliveredAt: null, lastError: null } : item)
    return ok({ delivery: deliveries.find(item => item.id === id) })
  }
  match = pathname.match(/^\/api\/partner\/manage\/webhooks\/([^/]+)$/)
  if (match && method === 'PATCH') {
    const id = decodeURIComponent(match[1])
    webhooks = webhooks.map(item => item.id === id ? { ...item, active: Boolean(body.active) } : item)
    return ok({ webhook: webhooks.find(item => item.id === id) })
  }

  match = pathname.match(/^\/api\/hiring\/roles\/([^/]+)\/applications$/)
  if (match && method === 'GET') {
    const status = url.searchParams.get('status')
    const city = (url.searchParams.get('city') || '').toLowerCase()
    const filtered = applications.filter(item => (!status || item.status === status) && (!city || item.location.city.toLowerCase().includes(city)))
    return ok({ applications: filtered, page: { nextCursor: null } })
  }
  match = pathname.match(/^\/api\/hiring\/roles\/([^/]+)$/)
  if (match && method === 'GET') {
    const role = roles.find(item => item.id === decodeURIComponent(match[1]))
    return ok({ role: role ? rolePublic(role) : null })
  }
  if (pathname === '/api/hiring/my-applications' && method === 'GET') return ok({ applications: myApplication ? [{ ...myApplication, role: { id: myApplication.roleId, title: 'Prep cook — restaurant kitchen', status: 'open' }, company: { name: org.name } }] : [], page: { nextCursor: null } })
  match = pathname.match(/^\/api\/hiring\/applications\/([^/]+)$/)
  if (match && method === 'GET') return ok({ application: myApplication ? { ...myApplication, questions: roles.find(role => role.id === myApplication.roleId)?.questions || [], role: { id: myApplication.roleId, title: 'Prep cook — restaurant kitchen', status: 'open' }, company: { name: org.name } } : null })
  match = pathname.match(/^\/api\/hiring\/applications\/([^/]+)\/withdraw$/)
  if (match && method === 'POST' && myApplication) { myApplication.status = 'withdrawn'; return ok({ application: myApplication }) }
  match = pathname.match(/^\/api\/hiring\/roles\/([^/]+)\/my-application$/)
  if (match && method === 'GET') return ok({ application: myApplication })
  match = pathname.match(/^\/api\/hiring\/roles\/([^/]+)\/apply$/)
  if (match && method === 'POST') {
    myApplication = { ...application('app-preview-user', 'c1', 'assessment_required', 0), candidate: { id: 'preview-user', name: 'Preview Applicant' }, roleId: decodeURIComponent(match[1]), location: body.location, answers: body.answers }
    applications = [myApplication, ...applications]
    return ok({ application: myApplication })
  }
  match = pathname.match(/^\/api\/hiring\/applications\/([^/]+)\/attempts\/start$/)
  if (match && method === 'POST') return ok({ launchUrl: 'https://cookcredit-knife-demo.web.app/' })

  return { handled: false }
}
