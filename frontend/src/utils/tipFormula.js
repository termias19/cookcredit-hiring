/**
 * Mise tip formula — v3
 * Added: ingredientOwner modes
 *   'house'  — shared supplies, normal formula
 *   'cook'   — cook buying ingredients, adds reimbursement estimate
 *   'eater'  — eaters bring their own, labor-only tip
 */

const BASE = 8.00

const INGREDIENT_TIERS = {
  basic: {
    multiplier: 0.3,
    costPerUnit: 0.50,
    keywords: [
      'salt','pepper','oil','olive oil','water','sugar','flour','butter',
      'garlic','onion','onions','garlic powder','paprika','cumin','oregano',
      'basil','thyme','vinegar','soy sauce','baking soda','baking powder',
      'cornstarch','bay leaf','bay leaves','cinnamon','chili flakes','red pepper'
    ]
  },
  standard: {
    multiplier: 0.7,
    costPerUnit: 2.00,
    keywords: [
      'tomato','tomatoes','potato','potatoes','carrot','carrots','celery',
      'spinach','lettuce','kale','broccoli','cauliflower','zucchini','cucumber',
      'bell pepper','mushroom','mushrooms','corn','peas','beans','lentils',
      'pasta','rice','bread','egg','eggs','milk','cream','cheese','yogurt',
      'lemon','lime','orange','apple','banana','avocado','ginger','jalapeño'
    ]
  },
  premium: {
    multiplier: 1.4,
    costPerUnit: 5.00,
    keywords: [
      'chicken','beef','pork','lamb','turkey','duck','salmon','tuna','shrimp',
      'fish','tilapia','cod','steak','ground beef','bacon','sausage','ham',
      'tofu','tempeh','mozzarella','parmesan','feta','brie','goat cheese',
      'heavy cream','coconut milk','tahini','miso','harissa','pesto','anchovy'
    ]
  },
  luxury: {
    multiplier: 2.2,
    costPerUnit: 12.00,
    keywords: [
      'truffle','saffron','wagyu','lobster','crab','scallops','oysters',
      'foie gras','caviar','prosciutto','aged cheese','black garlic',
      'uni','sea urchin','iberico','matsutake','morel'
    ]
  }
}

export function getIngredientTier(ingredient) {
  const normalized = ingredient.toLowerCase().trim()
  for (const [tier, config] of Object.entries(INGREDIENT_TIERS)) {
    if (config.keywords.some(k => normalized.includes(k) || k.includes(normalized))) {
      return { tier, multiplier: config.multiplier, costPerUnit: config.costPerUnit }
    }
  }
  return { tier: 'standard', multiplier: 0.7, costPerUnit: 2.00 }
}

export function deduplicateIngredients(ingredients) {
  const seen = new Set()
  return ingredients.filter(ing => {
    const key = ing.toLowerCase().trim()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function isDuplicate(ingredient, existingList) {
  const key = ingredient.toLowerCase().trim()
  return existingList.some(i => i.toLowerCase().trim() === key)
}

/**
 * Ingredient owner modes:
 *   'house' — shared supplies (default, normal formula)
 *   'cook'  — cook buys ingredients (adds reimbursement)
 *   'eater' — eaters bring ingredients (labor only, no ingredient bonuses)
 */
export function calculateTip({
  ingredients = [],
  servings = 2,
  cookRating = 0,
  cookReviews = 0,
  postedAt = new Date(),
  ingredientOwner = 'house',
  prepTime = 'medium',   // 'quick' | 'medium' | 'involved'
  windowHours = 2        // 0 = until I start, 1, 2, 4
}) {
  const unique = deduplicateIngredients(ingredients)

  // Servings bonus — always applies regardless of ingredient owner
  const servingsCapped = Math.min(servings, 10)
  const servingsBonus = servingsCapped * 1.50

  // Ingredient scoring — depends on who owns them
  const cappedIngredients = unique.slice(0, 8)
  const tieredIngredients = cappedIngredients.map(ing => ({
    name: ing,
    ...getIngredientTier(ing)
  }))

  let ingredientsBonus = 0
  let reimbursementEstimate = 0
  let complexityBonus = 0

  if (ingredientOwner === 'eater') {
    // Eater brings ingredients — tip is pure labor
    // No ingredient or complexity bonus — cook just shows up and cooks
    ingredientsBonus = 0
    complexityBonus = 0
    reimbursementEstimate = 0
  } else if (ingredientOwner === 'cook') {
    // Cook buys ingredients — include labor complexity AND reimbursement estimate
    ingredientsBonus = +tieredIngredients.reduce((sum, i) => sum + i.multiplier, 0).toFixed(2)
    complexityBonus = unique.length >= 5 ? 2.00 : 0
    // Rough cost estimate per serving based on ingredient tiers
    const rawCost = tieredIngredients.reduce((sum, i) => sum + i.costPerUnit, 0)
    reimbursementEstimate = +(rawCost * Math.min(servings, 10) * 0.4).toFixed(2) // 40% of estimated cost
  } else {
    // 'house' — shared supplies, standard formula
    ingredientsBonus = +tieredIngredients.reduce((sum, i) => sum + i.multiplier, 0).toFixed(2)
    complexityBonus = unique.length >= 5 ? 2.00 : 0
    reimbursementEstimate = 0
  }

  // Rating bonus — always applies
  const ratingBonus = cookReviews >= 3 ? +(cookRating * 0.80) : 0

  // Time of day bonus — derived from actual timestamp
  const hour = postedAt.getHours()
  let timeBonus = 0
  let timeLabel = ''
  if (hour >= 11 && hour < 14)      { timeBonus = 1.00; timeLabel = 'lunch' }
  else if (hour >= 18 && hour < 21) { timeBonus = 2.00; timeLabel = 'dinner' }
  else if (hour >= 21 || hour < 2)  { timeBonus = 3.00; timeLabel = 'late night' }
  else { timeLabel = 'other' }

  // Day of week bonus — weekends (Fri/Sat/Sun) are harder to give up
  const day = postedAt.getDay()
  const isWeekend = day === 0 || day === 5 || day === 6
  const weekendBonus = isWeekend ? 1.50 : 0

  // Prep time bonus — self-reported by cook
  const prepBonuses = { quick: 0, medium: 1.50, involved: 3.00 }
  const prepBonus = prepBonuses[prepTime] ?? 1.50

  // Urgency bonus — shorter window = higher bonus (inverse of window length)
  const urgencyBonuses = { 1: 2.00, 2: 1.00, 4: 0, 0: 0 }
  const urgencyBonus = urgencyBonuses[windowHours] ?? 0

  const laborTotal = BASE + servingsBonus + ingredientsBonus + complexityBonus + ratingBonus + timeBonus + weekendBonus + prepBonus + urgencyBonus
  const laborRounded = Math.round(laborTotal * 2) / 2
  const grandTotal = +(laborRounded + reimbursementEstimate).toFixed(2)

  return {
    total: grandTotal,
    laborTotal: laborRounded,
    reimbursementEstimate,
    ingredientOwner,
    perPerson: (n) => n > 0 ? +(grandTotal / n).toFixed(2) : grandTotal,
    breakdown: {
      base: BASE,
      servingsBonus: +servingsBonus.toFixed(2),
      ingredientsBonus,
      complexityBonus,
      ratingBonus: +ratingBonus.toFixed(2),
      timeBonus,
      timeLabel,
      weekendBonus,
      isWeekend,
      prepBonus,
      prepTime,
      urgencyBonus,
      windowHours,
      reimbursementEstimate,
      ingredientOwner,
      servingsCapped,
      uniqueIngredientCount: unique.length,
      cappedIngredientCount: cappedIngredients.length,
      tieredIngredients,
    }
  }
}

export function tipExplanation(breakdown) {
  const parts = []
  parts.push(`${breakdown.servingsCapped} servings`)
  if (breakdown.ingredientOwner === 'eater') {
    parts.push('labor only')
  } else if (breakdown.tieredIngredients?.length > 0) {
    const premiumCount = breakdown.tieredIngredients.filter(i => i.tier === 'premium' || i.tier === 'luxury').length
    parts.push(`${breakdown.cappedIngredientCount} ingredients${premiumCount > 0 ? ` (${premiumCount} premium)` : ''}`)
  }
  if (breakdown.prepBonus > 0) parts.push(`${breakdown.prepTime} prep`)
  if (breakdown.urgencyBonus > 0) parts.push(`${breakdown.windowHours}hr window`)
  if (breakdown.ingredientOwner === 'cook') parts.push('ingredient reimbursement')
  if (breakdown.ratingBonus > 0) parts.push('cook rating')
  if (breakdown.timeBonus > 0) parts.push(`${breakdown.timeLabel} time`)
  if (breakdown.weekendBonus > 0) parts.push('weekend')
  return parts.join(' · ')
}

export const PREP_TIME_OPTIONS = [
  { value: 'quick',    icon: '⚡', labelKey: 'prep_quick',    descKey: 'prep_quick_desc',    bonus: 0    },
  { value: 'medium',   icon: '🍳', labelKey: 'prep_medium',   descKey: 'prep_medium_desc',   bonus: 1.50 },
  { value: 'involved', icon: '👨‍🍳', labelKey: 'prep_involved', descKey: 'prep_involved_desc', bonus: 3.00 },
]

// Labels and descriptions for each mode — used in UI
export const INGREDIENT_OWNER_OPTIONS = [
  {
    value: 'house',
    icon: '🏠',
    labelKey: 'ing_owner_house',
    descKey: 'ing_owner_house_desc',
  },
  {
    value: 'cook',
    icon: '🛒',
    labelKey: 'ing_owner_cook',
    descKey: 'ing_owner_cook_desc',
  },
  {
    value: 'eater',
    icon: '👤',
    labelKey: 'ing_owner_eater',
    descKey: 'ing_owner_eater_desc',
  },
]

// Window urgency bonuses — used in UI to annotate window buttons
export const WINDOW_URGENCY = {
  1: { bonus: 2.00, label: '+$2 urgency' },
  2: { bonus: 1.00, label: '+$1 urgency' },
  4: { bonus: 0,    label: null },
  0: { bonus: 0,    label: null },
} 