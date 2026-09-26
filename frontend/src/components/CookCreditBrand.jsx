import { COOKCREDIT_SITE_URL } from '../config'

export default function CookCreditBrand({ compact = false }) {
  return <a href={COOKCREDIT_SITE_URL} aria-label="CookCredit home" className="cc-brand-link">
    {!compact && <img src="/cookcredit-mark-orange.svg" alt="" width="30" height="26" />}
    <span>Cook<span style={{ color: 'var(--cc-forest)' }}>Credit</span></span>
  </a>
}
