/**
 * Money + marketplace fee model — single source of truth.
 *
 * One booking has ONE subtotal (rate × hours). Two take-rates sit on top of it:
 *   - the eater pays a SERVICE_FEE on top of the subtotal, and
 *   - the cook is paid the subtotal minus a PLATFORM_FEE (commission).
 * Keeping both here means the eater total, the platform cut, and the cook payout
 * always reconcile — no screen invents its own percentages.
 */

import { MARKET } from '../config'
import { formatMoneyFor, regionFor } from './region'

export const SERVICE_FEE_RATE = 0.10 // eater pays this on top of the subtotal
export const PLATFORM_FEE_RATE = 0.15 // cook commission, deducted from the subtotal
// For UI copy — never hand-write "15%" in a screen; render this.
export const PLATFORM_FEE_PERCENT = Math.round(PLATFORM_FEE_RATE * 100)
export const SERVICE_FEE_PERCENT = Math.round(SERVICE_FEE_RATE * 100)

const round2 = (n) => Math.round((Number(n) || 0) * 100) / 100

/** subtotal = rate × hours */
export const subtotalOf = (rate, hours) => round2((Number(rate) || 0) * (Number(hours) || 0))

/** What the eater is charged: subtotal + service fee. */
export const eaterTotal = (subtotal) => round2((Number(subtotal) || 0) * (1 + SERVICE_FEE_RATE))
export const serviceFee = (subtotal) => round2((Number(subtotal) || 0) * SERVICE_FEE_RATE)

/** What the cook is paid: subtotal − platform commission. */
export const cookPayout = (subtotal) => round2((Number(subtotal) || 0) * (1 - PLATFORM_FEE_RATE))

/**
 * Currency is region-derived (utils/region.js): US -> "$45.00", ET -> "Br 1,200"
 * (whole birr, digit grouping). ETB stays in ETB — no cross-border conversion.
 * Safe formatter — never throws or prints NaN on undefined/strings.
 */
export const currency = () => regionFor(MARKET).currency
export const money = (n) => formatMoneyFor(MARKET, n)
