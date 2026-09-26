/**
 * Accreditation credibility — score a credential by its ACCREDITING BODY, never by brand.
 *
 * Two orthogonal axes per credential: (A) accreditation TRUST — where the issuer's standard sits in
 * the real chain (ANAB→CFP / ISO-17024 / ASTM E2659, DOL, CHEA) — and (B) VERIFICATION — did we
 * confirm the person actually holds it. Same-STANDARD exams are deliberately EQUAL: ANAB grants
 * national reciprocity, so a ServSafe Manager card and an NRFSP/Prometric/StateFoodSafety manager
 * card are the same credential at the same level — brand-ranking them would reproduce the gimmick
 * we're removing. Keys are the canonical taxonomy cert IDs (culinaryTaxonomy.js `certification` /
 * `alcohol_cert` categories), so the tier is a deterministic, auditable lookup — not a hardcoded
 * brand list, and never an embedding/similarity guess.
 *
 * The camera-VERIFIED skill score remains the un-forgeable anchor and is INDEPENDENT of this axis;
 * certCredibility is its own bounded ranking term a business can weight (a sushi bar weights a
 * food-protection-manager cert differently than a coffee bar) without ever displacing skill.
 */
import { labelOf } from '../data/culinaryTaxonomy'

// trust ∈ [0,1] by STANDARD + ACCREDITOR. Curated reference data, not code — tune here, audit here.
export const ACCREDITATION = {
  servsafe_manager:      { standard: 'CFP Food Protection Manager', accreditor: 'ANAB / CFP', trust: 1.00, kind: 'food_safety' },
  servsafe_food_handler: { standard: 'ASTM E2659 Food Handler',     accreditor: 'ANAB / ASTM', trust: 0.80, kind: 'food_safety' },
  food_handler_card:     { standard: 'ASTM E2659 Food Handler',     accreditor: 'ANAB / ASTM', trust: 0.80, kind: 'food_safety' },
  allergen_cert:         { standard: 'Allergen Awareness',          accreditor: 'Recognized',  trust: 0.30, kind: 'food_safety' },
  food_safety_cert:      { standard: 'Food-safety certification',   accreditor: 'Recognized',  trust: 0.55, kind: 'food_safety' },
  culinary_credential:   { standard: 'Culinary arts credential',    accreditor: 'School-dependent', trust: 0.55, kind: 'education' },
  // Alcohol-service certs are state-mandated where the ROLE's jurisdiction requires them — location-keyed,
  // never a blanket gate at apply time. Trust reflects a recognized state-accepted standard.
  servsafe_alcohol:      { standard: 'Responsible Alcohol Service', accreditor: 'State-mandated', trust: 0.80, kind: 'alcohol' },
  tabc:                  { standard: 'Responsible Alcohol Service', accreditor: 'TX TABC',     trust: 0.80, kind: 'alcohol' },
  rbs:                   { standard: 'Responsible Alcohol Service', accreditor: 'CA ABC (RBS)', trust: 0.80, kind: 'alcohol' },
  mast:                  { standard: 'Responsible Alcohol Service', accreditor: 'WA MAST',     trust: 0.80, kind: 'alcohol' },
  olcc:                  { standard: 'Responsible Alcohol Service', accreditor: 'OR OLCC',     trust: 0.80, kind: 'alcohol' },
  tips_cert:             { standard: 'Responsible Alcohol Service', accreditor: 'TIPS',        trust: 0.80, kind: 'alcohol' },
  // ACF individual certs (CC<CSC<CEC<CMC) are DOL-endorsed → trust 1.0 and a strong seniority signal.
  // Forward extension: add matching nodes to culinaryTaxonomy.js when the résumé scanner emits them.
  acf_cc:  { standard: 'ACF Certified Culinarian',        accreditor: 'ACF / DOL', trust: 1.00, kind: 'culinary' },
  acf_csc: { standard: 'ACF Certified Sous Chef',         accreditor: 'ACF / DOL', trust: 1.00, kind: 'culinary' },
  acf_cec: { standard: 'ACF Certified Executive Chef',    accreditor: 'ACF / DOL', trust: 1.00, kind: 'culinary' },
  acf_cmc: { standard: 'ACF Certified Master Chef',       accreditor: 'ACF / DOL', trust: 1.00, kind: 'culinary' },
}

// A CLAIM is discounted: an unverified credential, however reputable the issuer, can never out-credit
// a verified one. Résumé points are 'claimed' until a per-issuer lookup confirms them (Step B, later).
const VERIFICATION_FACTOR = { verified: 1.0, pending: 0.85, claimed: 0.70, unverifiable: 0.40, failed: 0.0 }

/** Deterministic display tier from the accreditation trust. */
export const trustTier = trust =>
  trust >= 0.95 ? 'Accredited'
    : trust >= 0.75 ? 'Accredited (training)'
      : trust >= 0.5 ? 'Recognized'
        : trust > 0 ? 'Self-reported' : 'Unverifiable'

/** One credential's [0,1] value = accreditation trust × verification factor. */
export function credentialValue(certId, status = 'claimed') {
  const a = ACCREDITATION[certId]
  if (!a) return 0
  return a.trust * (VERIFICATION_FACTOR[status] ?? VERIFICATION_FACTOR.claimed)
}

/**
 * certCredibilityScore — a candidate's overall [0,1] credential strength.
 * The single best credential anchors the score; further accredited credentials add a small,
 * diminishing breadth bonus (so two handler cards never out-credit one manager cert).
 *
 * @param {string[]} resumePoints  canonical taxonomy cert IDs
 * @param {object}   opts.statusById  optional per-cert verification status (default 'claimed')
 */
export function certCredibilityScore(resumePoints = [], { statusById = {} } = {}) {
  const vals = resumePoints
    .filter(id => ACCREDITATION[id])
    .map(id => credentialValue(id, statusById[id] || 'claimed'))
    .sort((a, b) => b - a)
  if (!vals.length) return 0
  const rest = vals.slice(1).reduce((s, v) => s + v, 0)
  return Math.max(0, Math.min(1, vals[0] + 0.15 * rest))
}

/** Display rows for the profile certifications section (sorted strongest accreditation first). */
export function credentialDetails(resumePoints = [], { statusById = {} } = {}) {
  return resumePoints
    .filter(id => ACCREDITATION[id])
    .map(id => {
      const a = ACCREDITATION[id]
      return { id, label: labelOf(id), standard: a.standard, accreditor: a.accreditor,
        trust: a.trust, tier: trustTier(a.trust), status: statusById[id] || 'claimed' }
    })
    .sort((x, y) => y.trust - x.trust)
}
