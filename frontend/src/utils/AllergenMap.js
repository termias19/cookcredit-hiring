/**
 * Mise allergen / dietary tag system — production build
 * Implements PDF spec: word-boundary regex, exceptions, qualifiers,
 * structured conflict objects, US Big 9 taxonomy, TAG_ALIASES.
 */

// ─── Tag taxonomy ────────────────────────────────────────────────────────────

export const DIETARY_TAGS = [
  { value: 'vegan',                     labelKey: 'tag_vegan',                     icon: '🌱',   category: 'diet' },
  { value: 'vegetarian',                labelKey: 'tag_vegetarian',                icon: '🥦',   category: 'diet' },
  { value: 'pescatarian',               labelKey: 'tag_pescatarian',               icon: '🐟',   category: 'diet' },
  // US Big 9
  { value: 'milk-free',                 labelKey: 'tag_milk_free',                 icon: '🥛',   category: 'allergen' },
  { value: 'egg-free',                  labelKey: 'tag_egg_free',                  icon: '🥚',   category: 'allergen' },
  { value: 'peanut-free',               labelKey: 'tag_peanut_free',               icon: '🥜',   category: 'allergen' },
  { value: 'tree-nut-free',             labelKey: 'tag_tree_nut_free',             icon: '🌰',   category: 'allergen' },
  { value: 'sesame-free',               labelKey: 'tag_sesame_free',               icon: '🫘',   category: 'allergen' },
  { value: 'soy-free',                  labelKey: 'tag_soy_free',                  icon: '🫛',   category: 'allergen' },
  { value: 'wheat-free',                labelKey: 'tag_wheat_free',                icon: '🌾',   category: 'allergen' },
  { value: 'fish-free',                 labelKey: 'tag_fish_free',                 icon: '🐠',   category: 'allergen' },
  { value: 'crustacean-shellfish-free', labelKey: 'tag_crustacean_shellfish_free', icon: '🦐',   category: 'allergen' },
  // Regulated claim
  { value: 'gluten-free',               labelKey: 'tag_gluten_free',               icon: '🚫🌾', category: 'claim' },
  // EU/UK optional
  { value: 'mollusk-free',              labelKey: 'tag_mollusk_free',              icon: '🦪',   category: 'allergen_optional' },
  { value: 'celery-free',               labelKey: 'tag_celery_free',               icon: '🥬',   category: 'allergen_optional' },
  { value: 'mustard-free',              labelKey: 'tag_mustard_free',              icon: '🌭',   category: 'allergen_optional' },
  { value: 'sulfite-free',              labelKey: 'tag_sulfite_free',              icon: '🍷',   category: 'allergen_optional' },
  { value: 'lupin-free',                labelKey: 'tag_lupin_free',                icon: '🌼',   category: 'allergen_optional' },
  // Religious
  { value: 'halal',                     labelKey: 'tag_halal',                     icon: '☪️',   category: 'religious' },
  { value: 'kosher',                    labelKey: 'tag_kosher',                    icon: '✡️',   category: 'religious' },
  // Lifestyle / heat
  { value: 'low-carb',                  labelKey: 'tag_low_carb',                  icon: '📉',   category: 'lifestyle' },
  { value: 'high-protein',              labelKey: 'tag_high_protein',              icon: '💪',   category: 'lifestyle' },
  { value: 'mild',                      labelKey: 'tag_mild',                      icon: '😌',   category: 'heat' },
  { value: 'spicy',                     labelKey: 'tag_spicy',                     icon: '🌶️',  category: 'heat' },
]

export const UNDETECTABLE_TAGS = ['halal','kosher','low-carb','high-protein','mild','spicy']

// Legacy tag expansion — keeps old Firestore values working
export const TAG_ALIASES = {
  'dairy-free':    ['milk-free'],
  'nut-free':      ['peanut-free','tree-nut-free'],
  'shellfish-free':['crustacean-shellfish-free','mollusk-free'],
}

// ─── Normalization & regex helpers ───────────────────────────────────────────

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function normalizeIngredientText(text) {
  return String(text || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function wordRegex(word, { plural = true } = {}) {
  const w = escapeRegExp(word)
  const suffix = plural ? '(s|es)?' : ''
  return new RegExp(`\\b${w}${suffix}\\b`, 'i')
}

function phraseRegex(phrase) {
  const parts = normalizeIngredientText(phrase).split(' ').filter(Boolean).map(escapeRegExp)
  if (parts.length === 0) return /$a/
  return new RegExp(`\\b${parts.join('\\s+')}\\b`, 'i')
}

// ─── Rule engine ─────────────────────────────────────────────────────────────

const TAG_RULES = {

  'milk-free': {
    qualifiers: [
      {
        id: 'plant_based_hint',
        regex: /\b(vegan|plant\s*based|non\s*dairy|dairy\s*free)\b/i,
        note: 'Ingredient line includes a plant-based/non-dairy qualifier (not a guarantee).',
        downgradeAmbiguousOnly: { confidenceMultiplier: 0.5, suggestedAction: 'VERIFY' },
      },
    ],
    exceptions: [
      { id: 'plant_milk',      regex: /\b(almond|oat|soy|coconut|rice|cashew|pea|hemp|flax)\s+milk\b/i, reason: 'Plant milk — not dairy.',      appliesTo: ['milk:milk'] },
      { id: 'cocoa_butter',    regex: /\bcocoa\s+butter\b/i,      reason: 'Cocoa butter is not dairy.',    appliesTo: ['milk:butter'] },
      { id: 'cream_of_tartar', regex: /\bcream\s+of\s+tartar\b/i, reason: 'Cream of tartar is not dairy.', appliesTo: ['milk:cream'] },
      { id: 'butter_lettuce',  regex: /\bbutter\s+lettuce\b/i,    reason: 'Butter lettuce is not dairy.',  appliesTo: ['milk:butter'] },
    ],
    patterns: [
      { id:'milk:casein',      keyword:'casein',       regex:wordRegex('casein',{plural:false}),  matchType:'word',   confidence:0.98, suggestedAction:'BLOCK', reason:'Milk protein (casein).' },
      { id:'milk:caseinate',   keyword:'caseinate',    regex:wordRegex('caseinate',{plural:true}), matchType:'word',   confidence:0.98, suggestedAction:'BLOCK', reason:'Milk protein (caseinate).' },
      { id:'milk:whey',        keyword:'whey',         regex:wordRegex('whey',{plural:false}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Milk protein (whey).' },
      { id:'milk:lactalbumin', keyword:'lactalbumin',  regex:wordRegex('lactalbumin',{plural:false}), matchType:'word', confidence:0.90, suggestedAction:'BLOCK', reason:'Milk-derived protein.' },
      { id:'milk:lactoglobulin',keyword:'lactoglobulin',regex:wordRegex('lactoglobulin',{plural:false}), matchType:'word', confidence:0.90, suggestedAction:'BLOCK', reason:'Milk-derived protein.' },
      { id:'milk:milk_protein',keyword:'milk protein', regex:phraseRegex('milk protein'),        matchType:'phrase', confidence:0.95, suggestedAction:'BLOCK', reason:'Explicit milk protein.' },
      { id:'milk:milk',        keyword:'milk',         regex:wordRegex('milk',{plural:false}),    matchType:'word',   confidence:0.75, suggestedAction:'WARN',  reason:'Milk/dairy word (could be plant milk).', ambiguous:true },
      { id:'milk:cream',       keyword:'cream',        regex:wordRegex('cream',{plural:false}),   matchType:'word',   confidence:0.70, suggestedAction:'WARN',  reason:'Cream/dairy term (ambiguous).', ambiguous:true },
      { id:'milk:cheese',      keyword:'cheese',       regex:wordRegex('cheese',{plural:false}),  matchType:'word',   confidence:0.85, suggestedAction:'BLOCK', reason:'Cheese is typically dairy.' },
      { id:'milk:butter',      keyword:'butter',       regex:wordRegex('butter',{plural:false}),  matchType:'word',   confidence:0.65, suggestedAction:'WARN',  reason:'Butter term (could be cocoa/seed/nut butter).', ambiguous:true },
      { id:'milk:yogurt',      keyword:'yogurt',       regex:wordRegex('yogurt',{plural:false}),  matchType:'word',   confidence:0.85, suggestedAction:'BLOCK', reason:'Yogurt is typically dairy.' },
      { id:'milk:ghee',        keyword:'ghee',         regex:wordRegex('ghee',{plural:false}),    matchType:'word',   confidence:0.85, suggestedAction:'BLOCK', reason:'Ghee is milk-derived fat.' },
      { id:'milk:half_and_half',keyword:'half and half',regex:phraseRegex('half and half'),       matchType:'phrase', confidence:0.90, suggestedAction:'BLOCK', reason:'Half-and-half is dairy.' },
      { id:'milk:sour_cream',  keyword:'sour cream',   regex:phraseRegex('sour cream'),           matchType:'phrase', confidence:0.90, suggestedAction:'BLOCK', reason:'Sour cream is dairy.' },
    ],
  },

  'egg-free': {
    qualifiers: [
      {
        id: 'vegan_eggfree_hint',
        regex: /\b(vegan|egg\s*free)\b/i,
        note: 'Ingredient line includes a vegan/egg-free qualifier (not a guarantee).',
        downgradeAmbiguousOnly: { confidenceMultiplier: 0.5, suggestedAction: 'VERIFY' },
      },
    ],
    exceptions: [
      { id:'eggplant',   regex:/\begg\s*plant\b/i,              reason:'Eggplant is not egg.', appliesTo:['egg:egg'] },
      { id:'vegan_mayo', regex:/\bvegan\s+(mayo|mayonnaise)\b/i, reason:'Explicit vegan mayo.', appliesTo:['egg:mayo'] },
    ],
    patterns: [
      { id:'egg:egg',      keyword:'egg',        regex:wordRegex('egg',{plural:true}),       matchType:'word',  confidence:0.92, suggestedAction:'BLOCK',  reason:'Egg ingredient.' },
      { id:'egg:albumen',  keyword:'albumen',    regex:wordRegex('albumen',{plural:false}),  matchType:'word',  confidence:0.90, suggestedAction:'BLOCK',  reason:'Egg protein (albumen).' },
      { id:'egg:ovalbumin',keyword:'ovalbumin',  regex:wordRegex('ovalbumin',{plural:false}),matchType:'word',  confidence:0.90, suggestedAction:'BLOCK',  reason:'Egg protein (ovalbumin).' },
      { id:'egg:mayo',     keyword:'mayonnaise', regex:/\b(mayo|mayonnaise)\b/i,             matchType:'regex', confidence:0.65, suggestedAction:'VERIFY', reason:'Mayo often contains egg but can be vegan.', ambiguous:true },
      { id:'egg:aioli',    keyword:'aioli',      regex:wordRegex('aioli',{plural:false}),    matchType:'word',  confidence:0.70, suggestedAction:'VERIFY', reason:'Aioli often contains egg.', ambiguous:true },
      { id:'egg:meringue', keyword:'meringue',   regex:wordRegex('meringue',{plural:false}), matchType:'word',  confidence:0.85, suggestedAction:'BLOCK',  reason:'Meringue is typically egg-based.' },
    ],
  },

  'peanut-free': {
    patterns: [
      { id:'peanut:peanut',        keyword:'peanut',        regex:wordRegex('peanut',{plural:true}),       matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Peanut ingredient.' },
      { id:'peanut:groundnut',     keyword:'groundnut',     regex:wordRegex('groundnut',{plural:true}),    matchType:'word',   confidence:0.85, suggestedAction:'BLOCK',  reason:'Groundnut is often peanut.' },
      { id:'peanut:peanut_butter', keyword:'peanut butter', regex:phraseRegex('peanut butter'),            matchType:'phrase', confidence:0.98, suggestedAction:'BLOCK',  reason:'Peanut butter.' },
      { id:'peanut:peanut_oil',    keyword:'peanut oil',    regex:phraseRegex('peanut oil'),               matchType:'phrase', confidence:0.60, suggestedAction:'VERIFY', reason:'Peanut oil may be highly refined; verify for allergy.', ambiguous:true },
    ],
  },

  'tree-nut-free': {
    patterns: [
      { id:'treenut:almond',    keyword:'almond',    regex:wordRegex('almond',{plural:true}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Tree nut (almond).' },
      { id:'treenut:cashew',    keyword:'cashew',    regex:wordRegex('cashew',{plural:true}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Tree nut (cashew).' },
      { id:'treenut:walnut',    keyword:'walnut',    regex:wordRegex('walnut',{plural:true}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Tree nut (walnut).' },
      { id:'treenut:pecan',     keyword:'pecan',     regex:wordRegex('pecan',{plural:true}),     matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Tree nut (pecan).' },
      { id:'treenut:pistachio', keyword:'pistachio', regex:wordRegex('pistachio',{plural:true}), matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Tree nut (pistachio).' },
      { id:'treenut:hazelnut',  keyword:'hazelnut',  regex:/\b(hazelnut|filbert)(s)?\b/i,        matchType:'regex',  confidence:0.95, suggestedAction:'BLOCK', reason:'Tree nut (hazelnut/filbert).' },
      { id:'treenut:macadamia', keyword:'macadamia', regex:wordRegex('macadamia',{plural:true}), matchType:'word',   confidence:0.90, suggestedAction:'BLOCK', reason:'Tree nut (macadamia).' },
      { id:'treenut:brazil_nut',keyword:'brazil nut',regex:phraseRegex('brazil nut'),            matchType:'phrase', confidence:0.90, suggestedAction:'BLOCK', reason:'Tree nut (Brazil nut).' },
      { id:'treenut:pine_nut',  keyword:'pine nut',  regex:phraseRegex('pine nut'),              matchType:'phrase', confidence:0.80, suggestedAction:'BLOCK', reason:'Pine nut often treated as tree nut.' },
      { id:'treenut:nut_butter',keyword:'nut butter',regex:/\b(almond|cashew|hazelnut|pistachio|walnut|pecan)\s+butter\b/i, matchType:'regex', confidence:0.90, suggestedAction:'BLOCK', reason:'Explicit tree nut butter.' },
    ],
  },

  'sesame-free': {
    patterns: [
      { id:'sesame:sesame',     keyword:'sesame',     regex:wordRegex('sesame',{plural:false}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Sesame ingredient.' },
      { id:'sesame:tahini',     keyword:'tahini',     regex:wordRegex('tahini',{plural:false}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK', reason:'Tahini is sesame paste.' },
      { id:'sesame:sesame_oil', keyword:'sesame oil', regex:phraseRegex('sesame oil'),             matchType:'phrase', confidence:0.90, suggestedAction:'BLOCK', reason:'Sesame oil.' },
      { id:'sesame:benne',      keyword:'benne',      regex:wordRegex('benne',{plural:false}),     matchType:'word',   confidence:0.85, suggestedAction:'BLOCK', reason:'Benne is a sesame alias.' },
      { id:'sesame:gingelly',   keyword:'gingelly',   regex:wordRegex('gingelly',{plural:false}),  matchType:'word',   confidence:0.85, suggestedAction:'BLOCK', reason:'Gingelly is a sesame alias.' },
      { id:'sesame:gomasio',    keyword:'gomasio',    regex:wordRegex('gomasio',{plural:false}),   matchType:'word',   confidence:0.85, suggestedAction:'BLOCK', reason:'Gomasio often contains sesame.' },
    ],
  },

  'soy-free': {
    exceptions: [
      // When "soy lecithin" appears, suppress the broad soy:soy BLOCK
      // so only the specific soy:lecithin VERIFY pattern fires (PDF test #6)
      { id:'soy_lecithin_suppress', regex:/\bsoy\s+lecithin\b/i, reason:'Soy lecithin handled by specific phrase pattern; suppress broad soy match.', appliesTo:['soy:soy'] },
    ],
    patterns: [
      { id:'soy:soy',      keyword:'soy',       regex:wordRegex('soy',{plural:false}),      matchType:'word',   confidence:0.85, suggestedAction:'BLOCK',  reason:'Soy ingredient.' },
      { id:'soy:soybean',  keyword:'soybean',   regex:wordRegex('soybean',{plural:true}),   matchType:'word',   confidence:0.90, suggestedAction:'BLOCK',  reason:'Soybean ingredient.' },
      { id:'soy:tofu',     keyword:'tofu',      regex:wordRegex('tofu',{plural:false}),     matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Tofu is soy.' },
      { id:'soy:tempeh',   keyword:'tempeh',    regex:wordRegex('tempeh',{plural:false}),   matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Tempeh is often soy.' },
      { id:'soy:edamame',  keyword:'edamame',   regex:wordRegex('edamame',{plural:false}),  matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Edamame is soy.' },
      { id:'soy:miso',     keyword:'miso',      regex:wordRegex('miso',{plural:false}),     matchType:'word',   confidence:0.85, suggestedAction:'BLOCK',  reason:'Miso is often soy-based.' },
      { id:'soy:soy_sauce',keyword:'soy sauce', regex:phraseRegex('soy sauce'),             matchType:'phrase', confidence:0.90, suggestedAction:'BLOCK',  reason:'Soy sauce contains soy.' },
      { id:'soy:tamari',   keyword:'tamari',    regex:wordRegex('tamari',{plural:false}),   matchType:'word',   confidence:0.80, suggestedAction:'VERIFY', reason:'Tamari is soy-based; verify.', ambiguous:true },
      { id:'soy:lecithin', keyword:'soy lecithin',regex:phraseRegex('soy lecithin'),        matchType:'phrase', confidence:0.45, suggestedAction:'VERIFY', reason:'Soy lecithin may be tolerated; verify.', ambiguous:true },
      { id:'soy:tvp',      keyword:'textured vegetable protein',regex:phraseRegex('textured vegetable protein'), matchType:'phrase', confidence:0.60, suggestedAction:'VERIFY', reason:'TVP is often soy; verify.', ambiguous:true },
    ],
  },

  'wheat-free': {
    patterns: [
      { id:'wheat:wheat',       keyword:'wheat',       regex:wordRegex('wheat',{plural:false}),       matchType:'word', confidence:0.95, suggestedAction:'BLOCK',  reason:'Wheat ingredient.' },
      { id:'wheat:durum',       keyword:'durum',       regex:wordRegex('durum',{plural:false}),       matchType:'word', confidence:0.90, suggestedAction:'BLOCK',  reason:'Durum is wheat.' },
      { id:'wheat:semolina',    keyword:'semolina',    regex:wordRegex('semolina',{plural:false}),    matchType:'word', confidence:0.90, suggestedAction:'BLOCK',  reason:'Semolina is wheat.' },
      { id:'wheat:spelt',       keyword:'spelt',       regex:wordRegex('spelt',{plural:false}),       matchType:'word', confidence:0.85, suggestedAction:'BLOCK',  reason:'Spelt is wheat.' },
      { id:'wheat:triticale',   keyword:'triticale',   regex:wordRegex('triticale',{plural:false}),   matchType:'word', confidence:0.85, suggestedAction:'BLOCK',  reason:'Triticale contains wheat.' },
      { id:'wheat:breadcrumbs', keyword:'breadcrumbs', regex:wordRegex('breadcrumb',{plural:true}),   matchType:'word', confidence:0.70, suggestedAction:'VERIFY', reason:'Breadcrumbs often contain wheat; verify.', ambiguous:true },
      { id:'wheat:flour',       keyword:'flour',       regex:wordRegex('flour',{plural:false}),       matchType:'word', confidence:0.65, suggestedAction:'VERIFY', reason:'Flour may be wheat or alternative; verify.', ambiguous:true },
    ],
  },

  'gluten-free': {
    qualifiers: [
      {
        id: 'gluten_free_label',
        regex: /\bgluten\s*free\b/i,
        note: 'Ingredient line explicitly labeled gluten-free.',
        suppressPatternIds: ['gluten:soy_sauce_heuristic','gluten:tamari_heuristic'],
      },
    ],
    exceptions: [
      { id:'gf_soy_sauce', regex:/\bgluten\s*free\s+soy\s+sauce\b/i, reason:'Explicit gluten-free soy sauce.', appliesTo:['gluten:soy_sauce_heuristic'] },
      { id:'gf_tamari',    regex:/\bgluten\s*free\s+tamari\b/i,       reason:'Explicit gluten-free tamari.',    appliesTo:['gluten:tamari_heuristic'] },
    ],
    patterns: [
      { id:'gluten:wheat',     keyword:'wheat',    regex:wordRegex('wheat',{plural:false}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Wheat contains gluten.' },
      { id:'gluten:barley',    keyword:'barley',   regex:wordRegex('barley',{plural:false}),   matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Barley contains gluten.' },
      { id:'gluten:rye',       keyword:'rye',      regex:wordRegex('rye',{plural:false}),      matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Rye contains gluten.' },
      { id:'gluten:malt',      keyword:'malt',     regex:wordRegex('malt',{plural:false}),     matchType:'word',   confidence:0.90, suggestedAction:'BLOCK',  reason:'Malt is often barley-derived.' },
      { id:'gluten:semolina',  keyword:'semolina', regex:wordRegex('semolina',{plural:false}), matchType:'word',   confidence:0.90, suggestedAction:'BLOCK',  reason:'Semolina is wheat.' },
      { id:'gluten:spelt',     keyword:'spelt',    regex:wordRegex('spelt',{plural:false}),    matchType:'word',   confidence:0.85, suggestedAction:'BLOCK',  reason:'Spelt is wheat.' },
      { id:'gluten:triticale', keyword:'triticale',regex:wordRegex('triticale',{plural:false}),matchType:'word',   confidence:0.85, suggestedAction:'BLOCK',  reason:'Triticale is a wheat/rye hybrid.' },
      { id:'gluten:soy_sauce_heuristic', keyword:'soy sauce', regex:phraseRegex('soy sauce'), matchType:'phrase', confidence:0.60, suggestedAction:'VERIFY', reason:'Many soy sauces contain wheat; verify gluten-free status.', ambiguous:true },
      { id:'gluten:tamari_heuristic',    keyword:'tamari',    regex:wordRegex('tamari',{plural:false}), matchType:'word', confidence:0.55, suggestedAction:'VERIFY', reason:'Tamari may contain wheat; verify.', ambiguous:true },
      { id:'gluten:flour',  keyword:'flour', regex:wordRegex('flour',{plural:false}), matchType:'word', confidence:0.60, suggestedAction:'VERIFY', reason:'Flour may be wheat or alternative; verify.', ambiguous:true },
      { id:'gluten:pasta',  keyword:'pasta', regex:wordRegex('pasta',{plural:false}), matchType:'word', confidence:0.60, suggestedAction:'VERIFY', reason:'Pasta may be wheat or gluten-free; verify.', ambiguous:true },
      { id:'gluten:oats',   keyword:'oats',  regex:wordRegex('oat',{plural:true}),    matchType:'word', confidence:0.40, suggestedAction:'VERIFY', reason:'Oats can be contaminated unless gluten-free certified.', ambiguous:true },
    ],
  },

  'fish-free': {
    patterns: [
      { id:'fish:fish',       keyword:'fish',       regex:wordRegex('fish',{plural:false}),      matchType:'word',   confidence:0.80, suggestedAction:'VERIFY', reason:'Generic fish reference; verify species.', ambiguous:true },
      { id:'fish:salmon',     keyword:'salmon',     regex:wordRegex('salmon',{plural:false}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Fish (salmon).' },
      { id:'fish:tuna',       keyword:'tuna',       regex:wordRegex('tuna',{plural:false}),      matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Fish (tuna).' },
      { id:'fish:cod',        keyword:'cod',        regex:wordRegex('cod',{plural:false}),       matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Fish (cod).' },
      { id:'fish:tilapia',    keyword:'tilapia',    regex:wordRegex('tilapia',{plural:false}),   matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Fish (tilapia).' },
      { id:'fish:anchovy',    keyword:'anchovy',    regex:wordRegex('anchovy',{plural:true}),    matchType:'word',   confidence:0.95, suggestedAction:'BLOCK',  reason:'Fish (anchovy/anchovies).' },
      { id:'fish:fish_sauce', keyword:'fish sauce', regex:phraseRegex('fish sauce'),             matchType:'phrase', confidence:0.95, suggestedAction:'BLOCK',  reason:'Fish sauce contains fish.' },
    ],
  },

  'crustacean-shellfish-free': {
    patterns: [
      { id:'crust:shrimp',   keyword:'shrimp',   regex:wordRegex('shrimp',{plural:false}),   matchType:'word', confidence:0.98, suggestedAction:'BLOCK', reason:'Crustacean shellfish (shrimp).' },
      { id:'crust:prawn',    keyword:'prawn',    regex:wordRegex('prawn',{plural:true}),     matchType:'word', confidence:0.90, suggestedAction:'BLOCK', reason:'Crustacean shellfish (prawn).' },
      { id:'crust:crab',     keyword:'crab',     regex:wordRegex('crab',{plural:true}),      matchType:'word', confidence:0.98, suggestedAction:'BLOCK', reason:'Crustacean shellfish (crab).' },
      { id:'crust:lobster',  keyword:'lobster',  regex:wordRegex('lobster',{plural:true}),   matchType:'word', confidence:0.98, suggestedAction:'BLOCK', reason:'Crustacean shellfish (lobster).' },
      { id:'crust:crayfish', keyword:'crayfish', regex:wordRegex('crayfish',{plural:false}), matchType:'word', confidence:0.90, suggestedAction:'BLOCK', reason:'Crustacean shellfish (crayfish).' },
    ],
  },

  'mollusk-free': {
    patterns: [
      { id:'mollusk:clam',     keyword:'clam',     regex:wordRegex('clam',{plural:true}),     matchType:'word', confidence:0.95, suggestedAction:'BLOCK', reason:'Mollusk (clam).' },
      { id:'mollusk:oyster',   keyword:'oyster',   regex:wordRegex('oyster',{plural:true}),   matchType:'word', confidence:0.95, suggestedAction:'BLOCK', reason:'Mollusk (oyster).' },
      { id:'mollusk:mussel',   keyword:'mussel',   regex:wordRegex('mussel',{plural:true}),   matchType:'word', confidence:0.95, suggestedAction:'BLOCK', reason:'Mollusk (mussel).' },
      { id:'mollusk:scallop',  keyword:'scallop',  regex:wordRegex('scallop',{plural:true}),  matchType:'word', confidence:0.95, suggestedAction:'BLOCK', reason:'Mollusk (scallop).' },
      { id:'mollusk:calamari', keyword:'calamari', regex:wordRegex('calamari',{plural:false}),matchType:'word', confidence:0.95, suggestedAction:'BLOCK', reason:'Mollusk (squid/calamari).' },
      { id:'mollusk:octopus',  keyword:'octopus',  regex:wordRegex('octopus',{plural:false}), matchType:'word', confidence:0.95, suggestedAction:'BLOCK', reason:'Mollusk (octopus).' },
    ],
  },

  'celery-free':  { patterns: [{ id:'celery:celery',   keyword:'celery',  regex:wordRegex('celery',{plural:false}),  matchType:'word', confidence:0.90, suggestedAction:'BLOCK',  reason:'Celery ingredient.' }] },
  'mustard-free': { patterns: [{ id:'mustard:mustard', keyword:'mustard', regex:wordRegex('mustard',{plural:false}), matchType:'word', confidence:0.90, suggestedAction:'BLOCK',  reason:'Mustard ingredient.' }] },
  'sulfite-free': { patterns: [{ id:'sulfite:sulfite', keyword:'sulfite', regex:wordRegex('sulfite',{plural:true}),  matchType:'word', confidence:0.85, suggestedAction:'VERIFY', reason:'Sulfites may be listed in various forms; verify.', ambiguous:true }] },
  'lupin-free':   { patterns: [{ id:'lupin:lupin',     keyword:'lupin',   regex:wordRegex('lupin',{plural:false}),   matchType:'word', confidence:0.90, suggestedAction:'BLOCK',  reason:'Lupin ingredient.' }] },

  vegan: {
    patterns: [
      { id:'vegan:meat',    keyword:'meat',    regex:/\b(beef|pork|chicken|turkey|lamb|duck|bacon|ham|sausage|prosciutto|pancetta|lard)\b/i,  matchType:'regex', confidence:0.90, suggestedAction:'BLOCK',  reason:'Animal meat.' },
      { id:'vegan:fish',    keyword:'fish',    regex:/\b(fish|salmon|tuna|cod|tilapia|anchovy|anchovies|fish\s+sauce)\b/i,                    matchType:'regex', confidence:0.90, suggestedAction:'BLOCK',  reason:'Fish/seafood.' },
      { id:'vegan:dairy',   keyword:'dairy',   regex:/\b(milk|cream|cheese|butter|yogurt|ghee|whey|casein)\b/i,                              matchType:'regex', confidence:0.80, suggestedAction:'VERIFY', reason:'Possible dairy; verify plant-based alternatives.', ambiguous:true },
      { id:'vegan:egg',     keyword:'egg',     regex:/\begg(s)?\b/i,                                                                          matchType:'regex', confidence:0.85, suggestedAction:'BLOCK',  reason:'Egg.' },
      { id:'vegan:honey',   keyword:'honey',   regex:/\bhoney\b/i,                                                                            matchType:'regex', confidence:0.85, suggestedAction:'BLOCK',  reason:'Honey.' },
      { id:'vegan:gelatin', keyword:'gelatin', regex:/\bgelatin\b/i,                                                                          matchType:'regex', confidence:0.90, suggestedAction:'BLOCK',  reason:'Gelatin is typically animal-derived.' },
    ],
  },

  vegetarian: {
    exceptions: [
      { id:'chamomile', regex:/\bchamomile\b/i, reason:'Avoid ham→chamomile false positive.', appliesTo:[] },
    ],
    patterns: [
      { id:'veg:meat', keyword:'meat', regex:/\b(beef|pork|chicken|turkey|lamb|duck|bacon|ham|sausage|prosciutto|pancetta|lard)\b/i, matchType:'regex', confidence:0.90, suggestedAction:'BLOCK', reason:'Animal meat.' },
      { id:'veg:fish', keyword:'fish', regex:/\b(fish|salmon|tuna|cod|tilapia|anchovy|anchovies|fish\s+sauce)\b/i,                  matchType:'regex', confidence:0.90, suggestedAction:'BLOCK', reason:'Fish/seafood (not vegetarian).' },
    ],
  },

  pescatarian: {
    patterns: [
      { id:'pesc:meat', keyword:'meat', regex:/\b(beef|pork|chicken|turkey|lamb|duck|bacon|ham|sausage|prosciutto|pancetta|lard)\b/i, matchType:'regex', confidence:0.90, suggestedAction:'BLOCK', reason:'Meat/poultry (not pescatarian).' },
    ],
  },
}

// ─── Core matching engine ─────────────────────────────────────────────────────

function expandDietaryTags(dietaryTags = []) {
  const out = new Set()
  for (const raw of dietaryTags || []) {
    const tag = String(raw || '').trim()
    if (!tag) continue
    TAG_ALIASES[tag] ? TAG_ALIASES[tag].forEach(t => out.add(t)) : out.add(tag)
  }
  return Array.from(out)
}

function applyExceptions(norm, pattern, exceptions = []) {
  for (const ex of exceptions) {
    const applies = !ex.appliesTo || ex.appliesTo.length === 0 || ex.appliesTo.includes(pattern.id)
    if (applies && ex.regex.test(norm)) return ex
  }
  return null
}

function analyzeIngredientAgainstTag(ingredientRaw, tag) {
  const rule = TAG_RULES[tag]
  if (!rule) return []

  const norm          = normalizeIngredientText(ingredientRaw)
  const qualifiers    = rule.qualifiers || []
  const exceptions    = rule.exceptions || []
  const patterns      = rule.patterns   || []
  const qualifierHits = qualifiers.filter(q => q.regex.test(norm))
  const matches       = []

  for (const p of patterns) {
    const m = norm.match(p.regex)
    if (!m) continue

    const ex = applyExceptions(norm, p, exceptions)
    if (ex) continue

    let confidence      = p.confidence
    let suggestedAction = p.suggestedAction
    const notes         = []

    for (const q of qualifierHits) {
      if (q.suppressPatternIds && q.suppressPatternIds.includes(p.id)) {
        notes.push(q.note || 'Qualifier suppresses this heuristic match.')
        confidence      = 0
        suggestedAction = 'NONE'
      }
      if (p.ambiguous && q.downgradeAmbiguousOnly) {
        const { confidenceMultiplier, suggestedAction: newAction } = q.downgradeAmbiguousOnly
        confidence      = Math.max(0, Math.min(1, confidence * (confidenceMultiplier ?? 1)))
        suggestedAction = newAction || suggestedAction
        if (q.note) notes.push(q.note)
      }
    }

    if (suggestedAction === 'NONE' || confidence === 0) continue

    matches.push({
      tag,
      ingredient:           ingredientRaw,
      normalizedIngredient: norm,
      matchedKeyword:       p.keyword,
      matchedText:          m[0],
      matchType:            p.matchType,
      confidence:           Number(confidence.toFixed(2)),
      suggestedAction,
      reason:               p.reason,
      notes,
      qualifierHits:        qualifierHits.map(q => q.id),
      patternId:            p.id,
    })
  }

  return matches
}

/**
 * Given ingredients and dietary tags, returns structured conflicts.
 * Return shape: { [tag]: { tag, conflicts: ConflictDetail[] } }
 */
export function detectConflicts(ingredients = [], dietaryTags = []) {
  const tags   = expandDietaryTags(dietaryTags)
  const result = {}
  for (const tag of tags) {
    if (UNDETECTABLE_TAGS.includes(tag)) continue
    const allMatches = []
    for (const ing of ingredients || []) {
      if (ing) allMatches.push(...analyzeIngredientAgainstTag(ing, tag))
    }
    if (allMatches.length > 0) result[tag] = { tag, conflicts: allMatches }
  }
  return result
}

/**
 * Check a single ingredient line against dietary tags.
 * Returns ConflictDetail[] (structured objects, not tag strings).
 */
export function ingredientConflictsWith(ingredient, dietaryTags = []) {
  const tags = expandDietaryTags(dietaryTags)
  const out  = []
  for (const tag of tags) {
    if (UNDETECTABLE_TAGS.includes(tag)) continue
    out.push(...analyzeIngredientAgainstTag(ingredient, tag))
  }
  return out
}

export function tagLabel(tag, t = {}) {
  const found = DIETARY_TAGS.find(d => d.value === tag)
  return found ? `${found.icon} ${t[found.labelKey] || tag}` : tag
} 