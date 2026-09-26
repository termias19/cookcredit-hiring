/**
 * Mise input sanitization utils
 *
 * Purpose:
 * - Strip characters that have no place in ingredient/dish/text fields
 * - Enforce length limits to prevent ReDoS on allergenMap regexes and DB bloat
 * - NOT a security silver bullet — Firebase rules + React JSX escaping are the
 *   primary defenses; this is an extra layer of hygiene
 */

// ─── Length limits ────────────────────────────────────────────────────────────
export const LIMITS = {
  dish:        80,   // dish name
  ingredient:  60,   // single ingredient
  bio:        500,   // cook bio
  notes:      500,   // booking notes
  displayName: 60,   // user name
  review:    1000,   // review text
}

// ─── Character allow-lists ────────────────────────────────────────────────────
// Allow letters (any Unicode script for multilingual support), digits,
// spaces, and common food punctuation. Strip everything else.
const INGREDIENT_ALLOWED = /[^\p{L}\p{N}\s\-,.'&%()]/gu
const TEXT_ALLOWED        = /[^\p{L}\p{N}\s\-.,!?'"@#%&*()\n]/gu

/**
 * Sanitize a dish name or ingredient:
 * - Trim whitespace
 * - Enforce max length
 * - Strip disallowed characters
 * - Collapse internal whitespace
 */
export function sanitizeIngredient(raw = '') {
  return String(raw)
    .trim()
    .slice(0, LIMITS.ingredient)
    .replace(INGREDIENT_ALLOWED, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export function sanitizeDish(raw = '') {
  return String(raw)
    .trim()
    .slice(0, LIMITS.dish)
    .replace(INGREDIENT_ALLOWED, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export function sanitizeText(raw = '', limit = LIMITS.bio) {
  return String(raw)
    .slice(0, limit)
    .replace(TEXT_ALLOWED, '')
    .replace(/[ \t]+/g, ' ')      // collapse horizontal whitespace, keep newlines
    .trim()
}

/**
 * Validate + sanitize a list of ingredients.
 * Returns { valid: string[], rejected: string[] }
 */
export function sanitizeIngredients(rawList = []) {
  const valid = []
  const rejected = []
  for (const raw of rawList) {
    const s = sanitizeIngredient(raw)
    if (s.length >= 2) valid.push(s)
    else if (s.length > 0) rejected.push(raw)
  }
  return { valid, rejected }
}

/**
 * Check if a string looks like an injection attempt.
 * Returns true if suspicious — used to show a warning, not hard-block.
 */
export function looksLikeMalicious(str = '') {
  const s = String(str).toLowerCase()
  return (
    /<\s*script/i.test(s)    ||
    /javascript:/i.test(s)   ||
    /on\w+\s*=/i.test(s)     ||   // onerror= onclick= etc
    /\$\{.+\}/.test(s)       ||   // template literal injection
    /__proto__|constructor|prototype/.test(s)  // prototype pollution
  )
} 