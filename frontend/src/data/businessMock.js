/** Development-only seed data for the CookCredit employer product tour. */
export const ORG = {
  id: 'org_demo', name: 'Juniper Hospitality Group', city: 'Atlanta, GA',
  loc: { lat: 33.755, lng: -84.39 }, cuisineFocus: ['Restaurant kitchens', 'Catering'], plan: 'trial',
}

export const CANDIDATES = [
  { id: 'c3', name: 'Mei Lin', bio: 'Pastry and garde-manger cook with twelve years across boutique hotels and private events.', city: 'Decatur, GA', tier: 'gold', verifiedScore: null, browserEstimate: 96, years: 12,
    cuisines: ['Pastry', 'Modern Asian'], assessed: 'Sep 2026', loc: { lat: 33.774, lng: -84.296 }, ratingMean: 5.0, reviewCount: 54, scoreAgeDays: 14, impressions: 900, acceptRate: 0.9,
    hasVideo: true, resumePoints: ['knife_skills', 'high_volume_prep', 'allergen_handling', 'soft_attention'] },
  { id: 'c1', name: 'Amara Okafor', bio: 'Prep cook with high-volume restaurant experience, consistent mise en place, and documented allergy accommodations.', city: 'Atlanta, GA', tier: 'gold', verifiedScore: null, browserEstimate: 93, years: 8,
    cuisines: ['West African', 'Southern'], assessed: 'Sep 2026', loc: { lat: 33.755, lng: -84.39 }, ratingMean: 4.9, reviewCount: 38, scoreAgeDays: 20, impressions: 700, acceptRate: 0.88,
    hasVideo: true, resumePoints: ['knife_skills', 'high_volume_prep', 'allergen_handling', 'prep_cook', 'soft_time_management'] },
  { id: 'c6', name: 'Priya Nair', bio: 'Private chef focused on vegetarian menus, dietary accommodations, and weekly batch cooking.', city: 'Atlanta, GA', tier: 'gold', verifiedScore: null, browserEstimate: 91, years: 9,
    cuisines: ['South Indian', 'Vegetarian'], assessed: 'Aug 2026', loc: { lat: 33.78, lng: -84.41 }, ratingMean: 4.9, reviewCount: 31, scoreAgeDays: 48, impressions: 650, acceptRate: 0.8,
    hasVideo: true, resumePoints: ['knife_skills', 'high_volume_prep', 'allergen_handling', 'allergen_handling'] },
  { id: 'c2', name: 'Diego Ramirez', bio: 'Line and prep cook with fast, repeatable knife work and high-volume service experience.', city: 'Atlanta, GA', tier: 'silver', verifiedScore: null, browserEstimate: 84, years: 5,
    cuisines: ['Mexican', 'New American'], assessed: 'Sep 2026', loc: { lat: 33.748, lng: -84.39 }, ratingMean: 4.7, reviewCount: 14, scoreAgeDays: 10, impressions: 240, acceptRate: 0.92,
    hasVideo: true, resumePoints: ['knife_skills', 'temperature_control', 'soft_teamwork'] },
  { id: 'c4', name: 'Sara Haile', bio: 'Catering cook with strong menu-planning fundamentals and experience with gluten-free and dairy-free requests.', city: 'Atlanta, GA', tier: 'silver', verifiedScore: null, browserEstimate: 84, years: 4,
    cuisines: ['Ethiopian', 'Mediterranean'], assessed: 'Aug 2026', loc: { lat: 33.762, lng: -84.4 }, ratingMean: 4.8, reviewCount: 12, scoreAgeDays: 35, impressions: 300, acceptRate: 0.85,
    hasVideo: true, resumePoints: ['knife_skills', 'high_volume_prep', 'allergen_handling', 'allergen_handling'] },
  { id: 'c5', name: 'Tom Becker', bio: 'Prep cook and baker available for early shifts, events, and weekly production work.', city: 'Marietta, GA', tier: 'bronze', verifiedScore: null, browserEstimate: 72, years: 3,
    cuisines: ['Bakery', 'American'], assessed: 'Jul 2026', loc: { lat: 33.953, lng: -84.549 }, ratingMean: 4.6, reviewCount: 9, scoreAgeDays: 70, impressions: 200, acceptRate: 0.8,
    hasVideo: true, resumePoints: ['knife_skills', 'soft_time_management'] },
  { id: 'c7', name: 'Jordan Blake', bio: 'Six years of kitchen experience listed on the résumé; the latest recorded knife result needs careful human review.', city: 'Atlanta, GA', tier: 'bronze', verifiedScore: null, browserEstimate: 58, years: 6,
    cuisines: ['American'], assessed: 'Sep 2026', loc: { lat: 33.76, lng: -84.38 }, ratingMean: 4.4, reviewCount: 7, scoreAgeDays: 8, impressions: 120, acceptRate: 0.75,
    hasVideo: true, resumePoints: ['knife_skills', 'high_volume_prep', 'soft_teamwork'] },
]

export const candidateById = id => CANDIDATES.find(candidate => candidate.id === id) || null

export const ROLES_SEED = [
  { id: 'r2', title: 'Prep cook — restaurant kitchen', status: 'open', loc: ORG.loc, radiusM: 50000,
    assessmentCriteria: { profileVersion: 'knife-motion-v1', minimumRhythm: 70, minimumConsistency: 70, minimumForm: 70 }, certsRequired: [], required: ['knife_skills', 'high_volume_prep'], preferred: ['allergen_handling', 'soft_time_management'] },
  { id: 'r1', title: 'Event cook — weekend service', status: 'open', loc: ORG.loc, radiusM: 60000,
    assessmentCriteria: { profileVersion: 'knife-motion-v1', minimumRhythm: 75, minimumConsistency: 70, minimumForm: 70 }, certsRequired: [], required: ['knife_skills', 'temperature_control'], preferred: ['soft_teamwork', 'allergen_handling'] },
  { id: 'r3', title: 'Private chef — weekly menus', status: 'draft', loc: ORG.loc, radiusM: 40000,
    assessmentCriteria: { profileVersion: 'knife-motion-v1', minimumRhythm: 85, minimumConsistency: 80, minimumForm: 75 }, certsRequired: [], required: ['high_volume_prep', 'allergen_handling'], preferred: ['allergen_handling', 'soft_communication'] },
]

export const PIPELINE_SEED = [
  { roleId: 'r2', cookId: 'c1', stage: 'shortlisted' },
  { roleId: 'r2', cookId: 'c4', stage: 'assessing' },
  { roleId: 'r2', cookId: 'c3', stage: 'assessing' },
  { roleId: 'r1', cookId: 'c2', stage: 'assessing' },
  { roleId: 'r1', cookId: 'c6', stage: 'shortlisted' },
  { roleId: 'r3', cookId: 'c5', stage: 'invited' },
]

export const STAGES = ['invited', 'assessing', 'verified', 'shortlisted', 'contacted', 'hired']
