/**
 * Fair cook ranking — surfacing cooks for eaters (recommender) and B2B screening (hiring).
 *
 * Verified knife-skill is the PRIMARY, criterion-valid signal (an actual work-sample of the
 * task — the strongest EEOC business-necessity defense). Everything else is a bounded, capped
 * relevance signal that can never buy down skill. The design follows the Indeed/LinkedIn
 * relevance + Uber/DoorDash geo-dispatch playbooks, hardened for fairness because the B2B
 * surface ranks people FOR HIRING (so it is legally an Automated Employment Decision Tool).
 *
 *   Stage 1 — HARD FILTER (feasibility only): in reach (Haversine vs the larger of the query
 *             radius and the cook's own travel radius), has a live verified score, available.
 *             Distance EXCLUDES here, so it never has to dominate a score to remove anyone.
 *   Stage 2 — TRANSPARENT WEIGHTED SUM on survivors (weights sum to 1.0), every term bounded
 *             [0,1] and logged as a named contribution for explainability + audit.
 *   Stage 3 — ORDER. B2B: deterministic (reproducible/auditable, human-in-the-loop makes the
 *             final cut). Eater feed: deterministic here; production should use merit-
 *             proportional STOCHASTIC exposure (Plackett-Luce + a reserved cold-start slot) so
 *             position bias doesn't amplify a tiny score gap into a huge attention gap.
 *
 * FAIRNESS, BY CONSTRUCTION:
 *   - Bayesian-shrunk ratings: a 5.0 with 2 reviews can't beat a 4.8 with 200; review count is
 *     a confidence weight, never raw rank power, so new cooks aren't buried or freak-rewarded.
 *   - Proximity is GATED + decayed + capped (0.12) and measured from the QUERY location the cook
 *     agreed to serve — NEVER home ZIP/neighborhood as a feature (algorithmic-redlining guard).
 *   - Experience is BUCKETED + capped + low-weight (raw years is an ADEA age proxy).
 *   - Cold-start EXPOSURE boost gives under-seen cooks a fair shot, bounded so it never outranks
 *     a genuinely better-skilled established cook (counters the rich-get-richer Matthew effect).
 *
 * NEVER a ranking signal (protected-attribute proxies): name, photo/appearance, gender, race,
 * age/DOB, exact neighborhood/ZIP as identity, national origin, language/accent, caregiver
 * status, free-text bio mined for the above, raw review count, or past booking-outcome labels.
 *
 * LEGAL (the B2B surface — surface counsel must own these before it gates anyone):
 *   - NYC Local Law 144: an AEDT needs an INDEPENDENT annual bias audit (publicly posted),
 *     >=10-business-day candidate notice, and an opt-out / alternative-process route.
 *   - EEOC Title VII: run the 4/5ths rule on the "top-K surfaced" event continuously (a rule of
 *     thumb, not a safe harbor); prove job-relatedness if adverse impact appears.
 *   - The verified-skill MODEL itself must be separately bias-audited (skin tone, handedness,
 *     camera angle, disability) and have an ADA accommodation / ALTERNATIVE assessment path.
 *   - Calibrate within groups; document that perfect fairness is impossible when base rates
 *     differ (Kleinberg/Pleiss) — claim a specific audited definition, never "fully fair".
 *
 * Pure functions, no React. Same code powers both surfaces; the caller picks `surface`.
 */

import { matchRole } from './match'
import { certCredibilityScore } from './accreditation'

// Every ranking term is bounded [0,1]; the weight vector decides their relative pull and always sums
// to 1.0 after normalizeWeights(). `cert` (accredited-credential strength), `match` (role fit) and
// `relevance` (search) are bounded add-ons — they reorder WITHIN the sum but can never buy down the
// verified-skill anchor, which a hard MIN_SKILL_SHARE floor keeps dominant no matter how a business
// tunes its weights. This is the "configurable per-business, not hardcoded" design: each org starts
// from a role-type TEMPLATE and may re-weight cert/experience/match/etc. freely above the floor.
export const TERM_KEYS = ['skill', 'cert', 'relevance', 'match', 'rating', 'proximity', 'cuisine', 'availability', 'experience', 'exposure']

export const MIN_SKILL_SHARE = 0.35   // verified skill can never be configured below this share (the EEOC anchor)

// Sensible defaults by role type so a new business is never blank — STORED + editable, not in code as
// the source of truth. food_safety_critical raises cert; precision (sushi/garde-manger) raises skill.
export const RANK_TEMPLATES = {
  default:              { skill: 0.42, cert: 0.10, relevance: 0.06, match: 0.06, rating: 0.13, proximity: 0.10, cuisine: 0.04, availability: 0.04, experience: 0.03, exposure: 0.02 },
  line_cook:            { skill: 0.45, cert: 0.10, relevance: 0.06, match: 0.07, rating: 0.10, proximity: 0.08, cuisine: 0.03, availability: 0.05, experience: 0.04, exposure: 0.02 },
  food_safety_critical: { skill: 0.40, cert: 0.20, relevance: 0.05, match: 0.06, rating: 0.10, proximity: 0.08, cuisine: 0.02, availability: 0.04, experience: 0.03, exposure: 0.02 },
  precision:            { skill: 0.55, cert: 0.08, relevance: 0.05, match: 0.06, rating: 0.10, proximity: 0.06, cuisine: 0.02, availability: 0.03, experience: 0.03, exposure: 0.02 },
}

/** Renormalize any (partial) weight vector to sum 1.0, then enforce the skill-dominance floor. */
export function normalizeWeights(w = {}, minSkillShare = MIN_SKILL_SHARE) {
  const out = {}
  let sum = 0
  for (const k of TERM_KEYS) { out[k] = Math.max(0, w[k] || 0); sum += out[k] }
  if (sum <= 0) return { ...RANK_TEMPLATES.default }
  for (const k of TERM_KEYS) out[k] /= sum
  if (out.skill < minSkillShare) {              // clamp skill up, scale the rest down proportionally
    const rest = (1 - out.skill) || 1
    const scale = (1 - minSkillShare) / rest
    for (const k of TERM_KEYS) out[k] = k === 'skill' ? minSkillShare : out[k] * scale
  }
  return out
}

/** Pick a template, apply the business's per-term overrides, drop `match` without a role, normalize. */
export function resolveWeights(query = {}, rankConfig = null) {
  const key = rankConfig?.template || query?.role?.template || query?.template
  const base = { ...(RANK_TEMPLATES[key] || RANK_TEMPLATES.default) }
  if (rankConfig?.weights) for (const k of TERM_KEYS) if (rankConfig.weights[k] != null) base[k] = rankConfig.weights[k]
  if (!query?.role) base.match = 0   // nothing to match against without a specific role
  return normalizeWeights(base, rankConfig?.minSkillShare ?? MIN_SKILL_SHARE)
}

const SKILL_HALF_LIFE_DAYS = 180   // verified score decays to 0.5 weight over ~6 months, floored
const RATING_PRIOR = 4.3           // global mean star prior for Bayesian shrinkage
const RATING_PRIOR_STRENGTH = 10   // K — equivalent to ~10 prior reviews
const PROX_OFFSET_M = 2000         // full proximity score within ~1.2 miles
const PROX_LAMBDA = Math.log(0.5) / 15000  // half score at 15 km, long tail beyond
const EXPOSURE_TAU = 200           // cold-start boost decays over ~200 impressions

export function haversineMeters(a, b) {
  if (!a || !b || a.lat == null || b.lat == null) return Infinity
  const R = 6371000, toRad = d => (d * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat), dLng = toRad(b.lng - a.lng)
  const s = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)))
}

function bayesShrink(mean, n, prior = RATING_PRIOR, K = RATING_PRIOR_STRENGTH) {
  if (!n) return prior
  return (n * mean + K * prior) / (n + K)
}

function expBucket(years) {
  const y = years || 0
  if (y < 1) return 0.25
  if (y < 3) return 0.5
  if (y < 7) return 0.75
  return 1.0
}

const clamp01 = x => Math.max(0, Math.min(1, x))

/** Stage 1 — feasibility filter (never scored). */
export function isFeasible(c, query = {}) {
  if (c.verifiedScore == null) return false
  if (query.skillFloor != null && c.verifiedScore < query.skillFloor) return false
  if (c.accepting === false) return false
  if (query.loc && (c.loc || c.travelRadiusM != null)) {
    const reach = Math.max(query.radiusM || 0, c.travelRadiusM || 0)
    if (reach > 0 && haversineMeters(query.loc, c.loc) > reach) return false
  }
  return true
}

/** Stage 2 — bounded, named terms + weighted total for one cook (weights from the per-business config). */
function scoreCook(c, query, rankConfig) {
  const ageDays = c.scoreAgeDays || 0
  const recency = Math.max(0.5, Math.exp(-Math.LN2 * ageDays / SKILL_HALF_LIFE_DAYS))
  const distM = query.loc && c.loc ? haversineMeters(query.loc, c.loc) : null

  const terms = {
    skill: clamp01((c.verifiedScore / 100) * recency),
    // accredited-credential strength (issuer accreditation × verification) — a NAMED, tunable term so a
    // business can weight certifications without ever displacing the verified-skill anchor.
    cert: clamp01(certCredibilityScore(c.resumePoints || [], { statusById: c.certStatus })),
    // search relevance from the client engine — bounded; reorders within the sum, never the sole sort key.
    relevance: query.relevance ? clamp01(query.relevance[c.id] ?? 0) : 0,
    // role fit — set only when ranking against a specific role (else 0, and resolveWeights zeroes its weight).
    match: query.role ? clamp01(matchRole(c, query.role).total) : 0,
    rating: clamp01(bayesShrink(c.ratingMean ?? RATING_PRIOR, c.reviewCount || 0) / 5),
    // a known distance decays; if the query has a location but the cook's is unknown, stay NEUTRAL
    // (0.5) rather than awarding full proximity — never advantage location-unknown cooks (redlining guard).
    proximity: distM != null ? clamp01(Math.exp(PROX_LAMBDA * Math.max(0, distM - PROX_OFFSET_M)))
      : query.loc ? 0.5 : 1,
    cuisine: query.cuisines && query.cuisines.length
      ? jaccard(query.cuisines, c.cuisines || []) : 1,
    availability: clamp01(0.6 * (c.inWindow === false ? 0 : 1) + 0.4 * Math.min(c.acceptRate ?? 1, 1)),
    experience: expBucket(c.years),
    exposure: Math.exp(-(c.impressions || 0) / EXPOSURE_TAU),
  }

  const W = resolveWeights(query, rankConfig)
  const contributions = {}
  let total = 0
  for (const k of TERM_KEYS) {
    contributions[k] = W[k] * (terms[k] ?? 0)
    total += contributions[k]
  }
  return {
    total,
    weights: W,
    contributions,
    inputs: { verifiedScore: c.verifiedScore, scoreAgeDays: ageDays, distanceKm: distM == null ? null : +(distM / 1000).toFixed(1),
      shrunkRating: +bayesShrink(c.ratingMean ?? RATING_PRIOR, c.reviewCount || 0).toFixed(2), reviewCount: c.reviewCount || 0 },
    reasons: reasonCodes(c, contributions, distM),
  }
}

function jaccard(a, b) {
  const A = new Set(a.map(x => x.toLowerCase())), B = new Set(b.map(x => x.toLowerCase()))
  if (!A.size) return 1
  let hit = 0
  for (const x of A) if (B.has(x)) hit++
  return hit / A.size
}

/** Top 2 contributors → plain-language reason codes (distance shown as a friendly tier). */
function reasonCodes(c, contributions, distM) {
  const friendly = {
    skill: `Verified skill ${c.verifiedScore}${c.scoreAgeDays != null ? ` (assessed ${c.scoreAgeDays}d ago)` : ''}`,
    rating: c.reviewCount ? `Rated ${(c.ratingMean ?? 0).toFixed(1)} (${c.reviewCount})` : 'New — limited reviews',
    proximity: distM == null ? null : distM <= PROX_OFFSET_M ? 'Within your area' : `${(distM / 1609).toFixed(1)} mi away`,
    cuisine: (c.cuisines || []).length ? `Cooks ${c.cuisines.slice(0, 2).join(', ')}` : null,
    availability: c.inWindow === false ? null : 'Available',
    experience: c.years ? `${c.years} yrs experience` : null,
    exposure: (c.impressions || 0) < EXPOSURE_TAU ? 'Newly verified' : null,
    match: 'Matches role requirements',
    cert: 'Accredited credentials',
    relevance: 'Matches your search',
  }
  return Object.entries(contributions)
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => friendly[k])
    .filter(Boolean)
    .slice(0, 3)
}

/**
 * Rank cooks. Returns a new array sorted best-first; each element is the original cook with a
 * `_rank` = { total, contributions, inputs, reasons } attached for display + audit logging.
 *
 * @param {Array} cooks
 * @param {Object} query  { loc:{lat,lng}, radiusM, cuisines:[], skillFloor, role, relevance:{id→[0,1]} }
 * @param {Object} opts   { surface:'b2b'|'eater', rankConfig }  — same math; B2B stays deterministic.
 *                        rankConfig = { template, weights:{...}, minSkillShare } (per-business, not hardcoded).
 */
export function rankCandidates(cooks, query = {}, { surface = 'b2b', rankConfig = null } = {}) {
  const ranked = cooks
    .filter(c => isFeasible(c, query))
    .map(c => ({ ...c, _rank: { ...scoreCook(c, query, rankConfig), surface } }))
    .sort((a, b) => b._rank.total - a._rank.total)
  // B2B MUST stay deterministic for auditability. The eater feed should reorder via stochastic
  // merit-proportional exposure (Plackett-Luce + a reserved cold-start slot) on top of this same
  // order — identical scores, fairer attention spread. `surface` is recorded on each _rank so the
  // audit log can reproduce which surface produced a given ranking.
  return ranked
}
