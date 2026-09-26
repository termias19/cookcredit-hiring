/**
 * Match engine — scores a cook against a role's SCORECARD (required vs preferred job-related
 * key-points), then feeds `ranking.js` as one bounded `match` term (it never replaces, and can
 * never buy down, the verified-skill anchor). Mirrors ranking.js's contract: bounded [0,1],
 * named breakdown, explainable reasons — so the same value drives the rank AND the audit log.
 *
 * Two stages (like ranking.js):
 *   A. HARD GATES — bona-fide deal-breakers only (a required food-safety cert, a skill floor).
 *      A gated candidate renders "Does not meet: ServSafe required" (auditable/ADA-defensible),
 *      never silently buried. Restricted to legally bona-fide requirements.
 *   B. REQUIREMENT COVERAGE — weighted coverage of required[] (taxonomy-adjacency: a child point
 *      satisfies a parent requirement) + a smaller preferred[] boost. Each requirement is met /
 *      not-met (NO keyword-density bonus → keyword-stuffing can't inflate rank). Knife/technique
 *      requirements may be satisfied by the UN-FORGEABLE camera-verified score, not just self-
 *      reported text.
 *
 * Fairness: anchors on the verified score, de-weights self-reported resume text, and only ranks
 * on job-related key-points (never name/age/school/ZIP). See ELITE_B2B_DESIGN.md + RANKING_FAIRNESS.md.
 */
import { satisfies, labelOf, nodeById } from '../data/culinaryTaxonomy'

const clamp01 = x => Math.max(0, Math.min(1, x))

/** Knife/technique requirements can be satisfied by the camera-verified score (the real signal). */
function isVerifiableSkill(id) {
  const n = nodeById(id)
  return !!n && n.category === 'technique'
}

/** Stage A — bona-fide hard gates. Returns { passed, failures[] }. */
export function hardGates(cook, role) {
  const failures = []
  const points = cook.resumePoints || []
  for (const certId of role.certsRequired || []) {
    if (!points.some(p => satisfies(p, certId))) failures.push(`Missing ${labelOf(certId)}`)
  }
  // Must-have skills are hard gates (capped at ~5 in post-a-role). A technique must-have can be
  // met by the camera-verified score; everything else needs a resume key-point. Roles created
  // before the structured scorecard have no `mustHave`, so this is a no-op for them.
  for (const id of role.mustHave || []) {
    const okResume = points.some(p => satisfies(p, id))
    const okVerified = isVerifiableSkill(id) && (cook.verifiedScore ?? 0) >= 70
    if (!okResume && !okVerified) failures.push(`Missing ${labelOf(id)}`)
  }
  if (role.skillFloor != null && (cook.verifiedScore ?? 0) < role.skillFloor) {
    failures.push(`Verified skill below ${role.skillFloor}`)
  }
  return { passed: failures.length === 0, failures }
}

/** Stage B — requirement coverage with per-requirement met/missing + source. */
export function requirementMatch(cook, role) {
  const points = cook.resumePoints || []
  const requirements = []
  const evalOne = (id, kind) => {
    const fromResume = points.some(p => satisfies(p, id))
    const fromVerified = isVerifiableSkill(id) && (cook.verifiedScore ?? 0) >= 70
    const met = fromResume || fromVerified
    requirements.push({
      id, label: labelOf(id), kind, status: met ? 'met' : 'missing',
      source: fromVerified ? `verified ${cook.verifiedScore}` : fromResume ? 'resume' : null,
    })
    return met
  }
  const required = role.required || []
  const preferred = role.preferred || []
  const reqMet = required.filter(id => evalOne(id, 'required')).length
  const prefMet = preferred.filter(id => evalOne(id, 'preferred')).length
  const reqCov = required.length ? reqMet / required.length : 1
  const prefCov = preferred.length ? prefMet / preferred.length : 0
  // required dominate; preferred is a smaller boost. Met/not-met only — no density bonus.
  const coverage = required.length ? clamp01(0.8 * reqCov + 0.2 * prefCov) : clamp01(prefCov)
  return { coverage, reqMet, reqTotal: required.length, prefMet, prefTotal: preferred.length, requirements }
}

/** Full match of one cook to one role → bounded total + coarse band + explainable breakdown. */
export function matchRole(cook, role) {
  const gates = hardGates(cook, role)
  const cov = requirementMatch(cook, role)
  const total = gates.passed ? cov.coverage : 0
  const band = !gates.passed ? 'Gated'
    : total >= 0.85 ? 'Strong fit'
    : total >= 0.6 ? 'Qualified'
    : total > 0 ? 'Partial' : 'Below'
  return { total, percent: Math.round(total * 100), band, gates, ...cov }
}

/**
 * Outside-the-box — reconcile resume CLAIMS against the camera-verified truth. A self-reported
 * knife-skill claim is corroborated, hedged, or CONTRADICTED by the un-forgeable verified score.
 * This is the inverse of keyword-stuffing: the camera signal vouches for (or catches) the resume.
 */
export function reconcileClaims(cook) {
  const points = cook.resumePoints || []
  const v = cook.verifiedScore
  const out = []
  if (points.some(p => satisfies(p, 'knife_skills')) && v != null) {
    out.push({
      claim: 'Knife skills (resume)',
      status: v >= 80 ? 'verified' : v >= 60 ? 'partial' : 'contradicted',
      detail: `camera-verified ${v}/100`,
    })
  }
  return out
}
