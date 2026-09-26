/**
 * Client-side relevance search over the ALREADY-LOADED roster (tens → low thousands of cooks).
 *
 * This is an instant filter+rank of a fetched page — NOT a scalable backend index. The scalable
 * replacement (Postgres FTS + pg_trgm fuzzy, then pgvector semantic + RRF hybrid) is the next layer;
 * see docs / the candidate-search research. Dependency-free by design: multi-field weighted fuzzy
 * matching with trigram-Dice typo tolerance, plus taxonomy-driven query expansion so a query
 * matches a cook's structured résumé even when the words differ ("fine dice" → a `brunoise` point,
 * "fabrication" / "breaking down" → `butchery`, "wok" → a Chinese-cuisine point).
 *
 * Two outputs, by surface:
 *   • FILTER  — `results` are the matches sorted by relevance (eater-style browse).
 *   • RE-RANK — `relevanceById` maps id→[0,1] to feed ranking.js as the bounded `relevance` term, so
 *               search relevance reorders WITHIN the fair weighted sum and never the sole sort key
 *               (it can never buy down the verified-skill anchor). Relevance scores only job-related
 *               fields; `name` is a lookup convenience here, never a ranking signal in ranking.js.
 */
import { nodeById, labelOf, ancestors } from '../data/culinaryTaxonomy'

// Field pull (top field = 1.0). A name hit edges a bio hit, but any field can satisfy a token.
const FIELD_BOOST = { name: 1.0, cuisines: 0.95, skills: 0.9, bio: 0.7, city: 0.6 }
const REL_FLOOR = 0.16   // below this, a candidate is not a match for the active query
const FUZZY_MIN = 0.60   // trigram-Dice threshold for a typo-tolerant token hit ("servsaffe" → ServSafe)

const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim()

function trigrams(s) {
  const t = `  ${s} `
  const g = new Set()
  for (let i = 0; i < t.length - 2; i++) g.add(t.slice(i, i + 3))
  return g
}
function dice(aG, b) {
  const bG = trigrams(b)
  if (!aG.size || !bG.size) return 0
  let inter = 0
  for (const x of aG) if (bG.has(x)) inter++
  return (2 * inter) / (aG.size + bG.size)
}

// Per-candidate searchable text, enriched via the taxonomy: each résumé point contributes its label,
// every alias, and its ancestor labels — that is the query expansion, deterministic and embedding-free.
function fields(c) {
  const skillTerms = []
  for (const id of c.resumePoints || []) {
    const n = nodeById(id)
    if (!n) { skillTerms.push(id); continue }
    skillTerms.push(n.label, ...(n.aliases || []))
    for (const anc of ancestors(id)) skillTerms.push(labelOf(anc))
  }
  return {
    name: norm(c.name),
    cuisines: norm((c.cuisines || []).join(' ')),
    skills: norm(skillTerms.join(' ')),
    bio: norm(c.bio || ''),
    city: norm(c.city || ''),
  }
}

// How well one query token matches one field's text: 1.0 if substring (exact/acronym), else the best
// trigram-Dice over the field's words (typo tolerance), gated by FUZZY_MIN.
function tokenInField(tokenG, token, text) {
  if (!text) return 0
  if (text.includes(token)) return 1
  let best = 0
  for (const w of text.split(' ')) {
    if (w.length < 2) continue
    const d = dice(tokenG, w)
    if (d > best) best = d
  }
  return best >= FUZZY_MIN ? best : 0
}

// Candidate relevance ∈ [0,1]: mean over query tokens of each token's best field-weighted match
// (so every typed token must be reasonably present — AND-ish — not just one of them).
function relevance(tokens, f) {
  if (!tokens.length) return 0
  let sum = 0
  for (const { token, g } of tokens) {
    let best = 0
    for (const field in FIELD_BOOST) {
      const s = FIELD_BOOST[field] * tokenInField(g, token, f[field])
      if (s > best) best = s
    }
    sum += best
  }
  return sum / tokens.length
}

/**
 * searchCandidates(query, candidates) → { active, results, relevanceById }
 *   active=false when the query is blank → results = candidates untouched, relevanceById = {}.
 *   active=true  → results are the matches (rel ≥ floor) sorted by relevance, each with `_searchRel`;
 *                  relevanceById carries every candidate's [0,1] relevance for the ranker.
 */
export function searchCandidates(query, candidates = []) {
  const q = norm(query)
  const tokens = q ? q.split(' ').filter(t => t.length >= 2).map(token => ({ token, g: trigrams(token) })) : []
  if (!tokens.length) return { active: false, results: candidates, relevanceById: {} }

  const relevanceById = {}
  const scored = []
  for (const c of candidates) {
    const rel = relevance(tokens, fields(c))
    relevanceById[c.id] = rel
    if (rel >= REL_FLOOR) scored.push({ c, rel })
  }
  scored.sort((a, b) => b.rel - a.rel)
  return { active: true, results: scored.map(s => ({ ...s.c, _searchRel: s.rel })), relevanceById }
}
