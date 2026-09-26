/**
 * Role-routed required-elements templates for post-a-role. Picking the ROLE first routes which
 * structured fields appear (cook gets stations + knife chips; server gets POS + location-keyed
 * alcohol cert; barista gets espresso/milk chips; dishwasher gets the physical + dish-machine
 * block). Every SCORED element carries a must-have (hard gate) vs preferred (soft weight) flag;
 * pay range is mandatory (pay-transparency law); physical requirements are ADA essential-function
 * framed. Skill ids reference culinaryTaxonomy. The free-text "About this role" box is NOT here —
 * it is captured separately and never enters the match. See ELITE_B2B_DESIGN.md.
 */
import { NODES } from './culinaryTaxonomy'

export const ROLES = [
  { id: 'prep_cook', label: 'Prep cook', group: 'cook' },
  { id: 'line_cook', label: 'Line cook', group: 'cook' },
  { id: 'lead_cook', label: 'Lead cook', group: 'cook' },
  { id: 'sous_chef', label: 'Sous chef', group: 'cook' },
  { id: 'private_chef', label: 'Private chef', group: 'cook' },
  { id: 'catering_cook', label: 'Catering cook', group: 'cook' },
]

export const EMPLOYMENT = ['Full-time', 'Part-time']
export const SHIFTS = ['Morning / open', 'Day', 'Evening', 'Night / close', 'Weekends', 'Holidays']
export const EXPERIENCE = ['No experience needed', 'Under 1 year', '1–2 years', '3+ years']
export const COOK_STATIONS = ['Grill', 'Sauté', 'Fry', 'Prep', 'Garde-manger']
export const PHYSICAL = [
  { id: 'lift_25', label: 'Lift up to 25 lb' },
  { id: 'lift_50', label: 'Lift up to 50 lb' },
  { id: 'stand_6', label: 'Stand / walk ~6 hrs' },
  { id: 'stand_8', label: 'Stand / walk ~8 hrs' },
]
export const FOOD_HANDLER_ID = 'food_safety_cert'   // taxonomy id used as a bona-fide cert gate
export const MAX_MUST_HAVES = 5                       // cap hard requirements; surface the rest as preferred

const byCat = c => NODES.filter(n => n.category === c).map(n => n.id)
const SOFT = byCat('soft')
const COOK_SKILLS = ['knife_skills', 'dice', 'julienne', 'brunoise', 'guillotine_cut', 'high_volume_prep', 'sauteing', 'grilling', 'sauce_making', 'plating', 'food_safety']
export const ROLE_TEMPLATE = {
  cook: { skills: COOK_SKILLS, soft: SOFT, station: true, foodHandler: true, tips: true,
    physicalDefault: [],
    verifiedAxis: { id: 'knife', live: true, label: 'Knife work: rhythm, consistency and form' } },
}

export const groupOf = roleId => (ROLES.find(r => r.id === roleId) || {}).group || 'cook'
export const templateFor = roleId => ROLE_TEMPLATE[groupOf(roleId)] || ROLE_TEMPLATE.cook
