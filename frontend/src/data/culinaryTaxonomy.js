/**
 * Culinary skill taxonomy — the single canonical vocabulary shared by the resume scanner
 * (emits these IDs), the role scorecard (requires these IDs), and the match engine (reasons
 * over them). A child node satisfies its parent, so a resume point `brunoise` covers a role
 * requirement of `knife_skills`. Curated (O*NET cook codes + ServSafe categories) and small
 * enough to hand-maintain at startup scale — the LinkedIn trie+parent/child pattern.
 *
 * Every node: { id, label, aliases[], parents[], category }.
 * category ∈ technique | cuisine | certification | station | food_safety
 * IDs here are JOB-RELATED ONLY — never name/age/school/location. (See RANKING_FAIRNESS.md.)
 */
export const NODES = [
  // ── techniques (knife skills + cooking methods) ──
  { id: 'knife_skills', label: 'Knife skills', aliases: ['knife skill', 'knifework', 'knife work'], parents: [], category: 'technique' },
  { id: 'brunoise', label: 'Brunoise', aliases: ['fine dice'], parents: ['knife_skills'], category: 'technique' },
  { id: 'julienne', label: 'Julienne', aliases: ['matchstick'], parents: ['knife_skills'], category: 'technique' },
  { id: 'dice', label: 'Dice', aliases: ['dicing', 'diced'], parents: ['knife_skills'], category: 'technique' },
  { id: 'chiffonade', label: 'Chiffonade', aliases: [], parents: ['knife_skills'], category: 'technique' },
  { id: 'batonnet', label: 'Batonnet', aliases: ['baton'], parents: ['knife_skills'], category: 'technique' },
  { id: 'rock_chop', label: 'Rock chop', aliases: ['rock chopping'], parents: ['knife_skills'], category: 'technique' },
  { id: 'guillotine_cut', label: 'Guillotine cut', aliases: ['guillotine dice', 'push cut'], parents: ['knife_skills'], category: 'technique' },
  { id: 'butchery', label: 'Butchery', aliases: ['butcher', 'fabrication', 'breaking down', 'filleting'], parents: ['knife_skills'], category: 'technique' },
  { id: 'high_volume_prep', label: 'High-volume prep', aliases: ['high volume', 'batch prep', 'volume prep'], parents: ['knife_skills'], category: 'technique' },
  { id: 'sauteing', label: 'Sautéing', aliases: ['saute', 'sauté'], parents: [], category: 'technique' },
  { id: 'grilling', label: 'Grilling', aliases: ['grill', 'broiling'], parents: [], category: 'technique' },
  { id: 'braising', label: 'Braising', aliases: ['braise'], parents: [], category: 'technique' },
  { id: 'roasting', label: 'Roasting', aliases: ['roast'], parents: [], category: 'technique' },
  { id: 'sauce_making', label: 'Sauce making', aliases: ['saucier', 'mother sauces', 'sauces'], parents: [], category: 'technique' },
  { id: 'baking', label: 'Baking', aliases: ['bake'], parents: [], category: 'technique' },
  { id: 'pastry', label: 'Pastry', aliases: ['patisserie', 'pastries'], parents: ['baking'], category: 'technique' },
  { id: 'plating', label: 'Plating & presentation', aliases: ['plating', 'presentation', 'garnish'], parents: [], category: 'technique' },
  { id: 'sous_vide', label: 'Sous vide', aliases: [], parents: [], category: 'technique' },

  // ── cuisines (stated preference only — never inferred from ethnicity/name) ──
  { id: 'italian', label: 'Italian', aliases: ['pasta', 'risotto'], parents: [], category: 'cuisine' },
  { id: 'mexican', label: 'Mexican', aliases: ['tex-mex', 'taqueria'], parents: [], category: 'cuisine' },
  { id: 'ethiopian', label: 'Ethiopian', aliases: ['injera', 'habesha'], parents: [], category: 'cuisine' },
  { id: 'french', label: 'French', aliases: ['classical french'], parents: [], category: 'cuisine' },
  { id: 'japanese', label: 'Japanese', aliases: ['sushi', 'izakaya'], parents: [], category: 'cuisine' },
  { id: 'chinese', label: 'Chinese', aliases: ['sichuan', 'cantonese', 'dim sum', 'wok'], parents: [], category: 'cuisine' },
  { id: 'indian', label: 'Indian', aliases: ['south indian', 'tandoor'], parents: [], category: 'cuisine' },
  { id: 'thai', label: 'Thai', aliases: [], parents: [], category: 'cuisine' },
  { id: 'southern_us', label: 'Southern', aliases: ['soul food', 'southern'], parents: [], category: 'cuisine' },
  { id: 'bbq', label: 'BBQ', aliases: ['barbecue', 'smoking', 'smoked'], parents: [], category: 'cuisine' },
  { id: 'mediterranean', label: 'Mediterranean', aliases: ['levantine'], parents: [], category: 'cuisine' },
  { id: 'west_african', label: 'West African', aliases: ['jollof'], parents: [], category: 'cuisine' },
  { id: 'vegan', label: 'Vegan', aliases: ['plant-based', 'plant based'], parents: [], category: 'cuisine' },
  { id: 'vegetarian', label: 'Vegetarian', aliases: [], parents: [], category: 'cuisine' },

  // ── certifications (food-safety credentials → can be bona-fide hard gates) ──
  { id: 'food_safety_cert', label: 'Food-safety certification', aliases: [], parents: [], category: 'certification' },
  { id: 'servsafe_manager', label: 'ServSafe Manager', aliases: ['servsafe manager', 'servsafe food protection manager'], parents: ['food_safety_cert'], category: 'certification' },
  { id: 'servsafe_food_handler', label: 'ServSafe Food Handler', aliases: ['servsafe food handler', 'servsafe handler'], parents: ['food_safety_cert'], category: 'certification' },
  { id: 'food_handler_card', label: 'Food Handler card', aliases: ['food handler', "food handler's card", 'food handlers card'], parents: ['food_safety_cert'], category: 'certification' },
  { id: 'allergen_cert', label: 'Allergen Awareness', aliases: ['allergen awareness', 'allergen certification'], parents: ['food_safety_cert'], category: 'certification' },
  { id: 'culinary_credential', label: 'Culinary credential', aliases: ['culinary degree', 'culinary diploma', 'culinary arts'], parents: [], category: 'certification' },

  // ── stations / roles ──
  { id: 'line_cook', label: 'Line cook', aliases: ['line cook', 'on the line'], parents: [], category: 'station' },
  { id: 'prep_cook', label: 'Prep cook', aliases: ['prep cook', 'prep'], parents: [], category: 'station' },
  { id: 'saute_station', label: 'Sauté station', aliases: ['saute station'], parents: [], category: 'station' },
  { id: 'grill_station', label: 'Grill station', aliases: ['grill cook'], parents: [], category: 'station' },
  { id: 'garde_manger', label: 'Garde manger', aliases: ['cold station', 'pantry'], parents: [], category: 'station' },
  { id: 'pastry_station', label: 'Pastry station', aliases: ['pastry chef', 'pastry cook'], parents: [], category: 'station' },
  { id: 'sous_chef', label: 'Sous chef', aliases: ['sous'], parents: [], category: 'station' },
  { id: 'expediter', label: 'Expediter', aliases: ['expo', 'expediting'], parents: [], category: 'station' },

  // ── food safety (knowledge, not a credential) ──
  { id: 'food_safety', label: 'Food safety', aliases: ['sanitation', 'safe food handling'], parents: [], category: 'food_safety' },
  { id: 'haccp', label: 'HACCP', aliases: [], parents: ['food_safety'], category: 'food_safety' },
  { id: 'allergen_handling', label: 'Allergen handling', aliases: ['allergen handling', 'cross-contamination'], parents: ['food_safety'], category: 'food_safety' },
  { id: 'temperature_control', label: 'Temperature control', aliases: ['temp control', 'cold chain'], parents: ['food_safety'], category: 'food_safety' },

  // ── server skills ──
  { id: 'tray_service', label: 'Tray / plate carrying', aliases: ['tray service', 'tray carrying', 'food running'], parents: [], category: 'server_skill' },
  { id: 'steps_of_service', label: 'Steps of service', aliases: ['fine dining service', 'table service'], parents: [], category: 'server_skill' },
  { id: 'split_check', label: 'Cash & split-check handling', aliases: ['split checks', 'cash handling'], parents: [], category: 'server_skill' },
  { id: 'allergen_knowledge', label: 'Allergen knowledge', aliases: ['allergens', 'menu knowledge'], parents: [], category: 'server_skill' },
  // ── barista skills ──
  { id: 'espresso_dialin', label: 'Espresso dial-in', aliases: ['espresso', 'pulling shots', 'dialing in'], parents: [], category: 'barista_skill' },
  { id: 'milk_steaming', label: 'Milk steaming / microfoam', aliases: ['steaming milk', 'microfoam', 'frothing'], parents: [], category: 'barista_skill' },
  { id: 'latte_art', label: 'Latte art', aliases: ['free pour', 'rosetta', 'latte-art'], parents: [], category: 'barista_skill' },
  { id: 'alt_milk', label: 'Alt-milk handling', aliases: ['oat milk', 'almond milk', 'non-dairy'], parents: [], category: 'barista_skill' },
  { id: 'machine_maintenance', label: 'Machine maintenance', aliases: ['backflush', 'descale', 'group head'], parents: [], category: 'barista_skill' },
  // ── dishwasher skills ──
  { id: 'dish_machine', label: 'Commercial dish machine', aliases: ['dish machine', 'dishmachine', 'hobart'], parents: [], category: 'dish_skill' },
  { id: 'three_comp_sink', label: 'Three-compartment sink', aliases: ['3-compartment sink', 'three compartment'], parents: [], category: 'dish_skill' },
  { id: 'rack_discipline', label: 'Rack & load sequencing', aliases: ['racking', 'load sequencing'], parents: [], category: 'dish_skill' },
  { id: 'dish_sanitation', label: 'Sanitation standards', aliases: ['warewashing', 'sanitizing'], parents: ['food_safety'], category: 'dish_skill' },
  // ── POS systems ──
  { id: 'pos_toast', label: 'Toast POS', aliases: ['toast'], parents: [], category: 'pos' },
  { id: 'pos_aloha', label: 'Aloha POS', aliases: ['aloha'], parents: [], category: 'pos' },
  { id: 'pos_micros', label: 'Micros POS', aliases: ['micros'], parents: [], category: 'pos' },
  { id: 'pos_square', label: 'Square POS', aliases: ['square'], parents: [], category: 'pos' },
  { id: 'pos_clover', label: 'Clover POS', aliases: ['clover'], parents: [], category: 'pos' },
  // ── alcohol-server certs (location-keyed; never a hard gate at apply time) ──
  { id: 'tabc', label: 'TABC (TX)', aliases: ['tabc'], parents: [], category: 'alcohol_cert' },
  { id: 'rbs', label: 'RBS (CA)', aliases: ['rbs', 'responsible beverage service'], parents: [], category: 'alcohol_cert' },
  { id: 'mast', label: 'MAST (WA)', aliases: ['mast'], parents: [], category: 'alcohol_cert' },
  { id: 'olcc', label: 'OLCC (OR)', aliases: ['olcc'], parents: [], category: 'alcohol_cert' },
  { id: 'tips_cert', label: 'TIPS', aliases: ['tips certified', 'tips certification'], parents: [], category: 'alcohol_cert' },
  { id: 'servsafe_alcohol', label: 'ServSafe Alcohol', aliases: ['servsafe alcohol'], parents: [], category: 'alcohol_cert' },
  // ── controlled soft-skill tags (low weight; never free text) ──
  { id: 'soft_teamwork', label: 'Teamwork', aliases: [], parents: [], category: 'soft' },
  { id: 'soft_customer_service', label: 'Customer service', aliases: ['guest service'], parents: [], category: 'soft' },
  { id: 'soft_time_management', label: 'Time management', aliases: [], parents: [], category: 'soft' },
  { id: 'soft_attention', label: 'Attention to detail', aliases: [], parents: [], category: 'soft' },
  { id: 'soft_communication', label: 'Communication', aliases: [], parents: [], category: 'soft' },
]

const BY_ID = Object.fromEntries(NODES.map(n => [n.id, n]))
export const nodeById = id => BY_ID[id] || null
export const labelOf = id => (BY_ID[id]?.label) || id

/** All ancestor IDs of a node (so a child can satisfy a parent requirement). */
export function ancestors(id, seen = new Set()) {
  const n = BY_ID[id]
  if (!n) return seen
  for (const p of n.parents) { if (!seen.has(p)) { seen.add(p); ancestors(p, seen) } }
  return seen
}

/** Does a resume point satisfy a requirement? Exact match OR the point is a descendant. */
export function satisfies(pointId, requirementId) {
  if (pointId === requirementId) return true
  return ancestors(pointId).has(requirementId)
}

/**
 * Fast client-side trie-ish pass: scan raw resume text for taxonomy labels/aliases.
 * Negation-aware (skips "no <term>" / "not <term>") to defeat negation blindness.
 * Returns [{ canonical_id, label, category, evidence_span, confidence }].
 */
export function scanText(text) {
  const lower = ` ${text.toLowerCase().replace(/\s+/g, ' ')} `
  const hits = new Map()
  for (const n of NODES) {
    const terms = [n.label.toLowerCase(), ...n.aliases.map(a => a.toLowerCase())]
    for (const term of terms) {
      let i = lower.indexOf(` ${term} `)
      if (i === -1) i = lower.indexOf(` ${term},`)
      if (i === -1) i = lower.indexOf(` ${term}.`)
      if (i === -1) continue
      const before = lower.slice(Math.max(0, i - 14), i)
      if (/\b(no|not|never|without|lack)\b/.test(before)) continue // negation guard
      const start = lower.indexOf(term, Math.max(0, i))
      hits.set(n.id, {
        canonical_id: n.id, label: n.label, category: n.category,
        evidence_span: text.slice(Math.max(0, start - 24), start + term.length + 24).trim(),
        confidence: term === n.label.toLowerCase() ? 0.95 : 0.8,
      })
      break
    }
  }
  return [...hits.values()]
}
