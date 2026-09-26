/**
 * Region — the single market/locale source of truth.
 *
 * Everything market-shaped derives from here: currency + formatting, payment
 * methods (display/selection only — actual charging is server-side), phone
 * country code + validation, default/available languages, distance units,
 * date locale, geography, tier colors, and business plan pricing.
 *
 * Single-market (US) build; REGION / money() / tierColor() are what normal
 * app code should use. regionFor()/formatMoneyFor() etc. still take an
 * explicit market argument for call-site flexibility, but only 'US' exists.
 *
 * No screen may hardcode '$', a payment list, or a fee percent.
 */

import { MARKET } from '../config'

const REGIONS = {
  US: {
    market: 'US',
    currency: { code: 'USD', symbol: '$', decimals: 2 },
    // Online methods shown at checkout. US card checkout (Stripe) isn't wired
    // yet, so cash-on-delivery is the only live method; the server enforces
    // what actually settles either way.
    payment: {
      online: [],
      payoutsLabel: 'Payouts via Stripe',
    },
    phone: {
      prefix: '+1',
      placeholder: '(555) 123-4567',
      // National-number digits after stripping the prefix / leading trunk 0.
      minDigits: 10, maxDigits: 10,
    },
    defaultLang: 'EN',
    languages: ['EN', 'ES', 'AM', 'TI', 'OM'],
    dateLocale: 'en-US',
    units: { distance: 'miles' },
    geo: { country: 'United States', city: 'Atlanta', hoods: [] },
    tierColors: { gold: '#C9A227', silver: '#9AA3AD', bronze: '#8A6A3A', fallback: '#1F6F5C' },
    business: { teamPlanPrice: 149 },
  },
}

export const regionFor = (market) => REGIONS[market] || REGIONS.US
export const REGION = regionFor(MARKET)

// Native language names, one shared table (pickers filter by REGION.languages).
export const LANG_LABELS = {
  EN: 'English', ES: 'Español', AM: 'አማርኛ', TI: 'ትግርኛ', OM: 'Afaan Oromoo',
}

/** "1,200" (ET) / "45.00" (US) — grouping always, decimals per market. */
export const formatMoneyFor = (market, n) => {
  const { symbol, decimals } = regionFor(market).currency
  const v = Number(n) || 0
  return symbol + v.toLocaleString('en-US', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  })
}

/** Credential tier color; accepts 'gold' | 'Gold' | null. */
export const tierColorFor = (market, tier) => {
  const t = regionFor(market).tierColors
  return t[String(tier || '').toLowerCase()] || t.fallback
}
export const tierColor = (tier) => tierColorFor(MARKET, tier)

/**
 * Checkout method list for display/selection: the market's online methods plus
 * cash-on-delivery. Labels for the (translated) COD entry are passed in.
 * The backend re-validates the chosen method — this list gates nothing.
 */
export const paymentMethodsFor = (market, { cod, codSub } = {}) => ([
  ...regionFor(market).payment.online,
  { id: 'cod', label: cod || 'Cash on delivery', sub: codSub },
])
export const paymentMethods = (labels) => paymentMethodsFor(MARKET, labels)

/**
 * Normalize a user-typed phone number to E.164 for THIS market:
 * strip separators, drop the country code if retyped, drop a leading trunk 0
 * (ET convention: 091 234 5678 -> +25191...), then prepend the prefix.
 * Returns null for an empty input.
 */
export const normalizePhone = (raw, market = MARKET) => {
  const { prefix } = regionFor(market).phone
  let digits = String(raw || '').replace(/\D/g, '')
  if (!digits) return null
  const cc = prefix.replace('+', '')
  if (digits.startsWith(cc)) digits = digits.slice(cc.length)
  digits = digits.replace(/^0+/, '')
  return `${prefix}${digits}`
}

/** True when empty (optional field) or a plausible national number for the market. */
export const isValidPhone = (raw, market = MARKET) => {
  const norm = normalizePhone(raw, market)
  if (norm == null) return true
  const { prefix, minDigits, maxDigits } = regionFor(market).phone
  const national = norm.slice(prefix.length)
  return national.length >= minDigits && national.length <= maxDigits
}
