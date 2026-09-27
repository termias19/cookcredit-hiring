import { useLang } from '../context/LangContext'

// Design system: Cormorant Garamond serif + monochrome (#1a1a1a / #555 / #777 / #999 / #e5e5e5),
// sharp corners. Green is reserved only for actionable elements.
const SERIF = "'Cormorant Garamond', Georgia, serif"
const GREEN = '#1F6F5C'

const SectionHead = ({ children }) => (
  <h3 style={{ fontFamily: SERIF, fontSize: 19, fontWeight: 600, color: '#1a1a1a', margin: '20px 0 6px' }}>{children}</h3>
)

const SubHead = ({ children }) => (
  <div style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', margin: '10px 0 4px' }}>{children}</div>
)

const Pill = ({ children, type }) => (
  <span style={{
    display: 'inline-block', padding: '3px 10px', borderRadius: 0, fontSize: 11, fontWeight: 600, margin: '0 4px 6px 0',
    border: `1px solid ${type === 'yes' ? GREEN : '#B4232A'}`,
    color: type === 'yes' ? GREEN : '#B4232A',
  }}>{children}</span>
)

const CompanyFooter = ({ text }) => (
  <div style={{ textAlign: 'center', padding: '16px 0', borderTop: '1px solid #e5e5e5', marginTop: 16 }}>
    <div style={{ fontSize: 12, fontWeight: 600, color: '#1a1a1a', letterSpacing: 0.3 }}>A Beni-Amer product</div>
    <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>{text}</div>
  </div>
)

const P = ({ children }) => <p style={{ margin: '0 0 10px', fontSize: 14, lineHeight: 1.6, color: '#555' }}>{children}</p>

export function AboutContent() {
  const { t } = useLang()
  return <>
    <div style={{ textAlign: 'center', padding: '12px 0 8px' }}>
      <div style={{ fontFamily: SERIF, fontSize: 30, fontWeight: 600, color: '#1a1a1a', letterSpacing: 1 }}>Mise</div>
      <div style={{ fontSize: 13, color: '#777', marginTop: 4 }}>{t.hero_tagline}</div>
    </div>
    <div style={{ width: 40, height: 1, background: '#e5e5e5', margin: '14px auto 16px' }} />
    <P>{t.about_p1}</P>
    <P>{t.about_p2}</P>
    <SectionHead>{t.about_how}</SectionHead>
    <P>{t.about_p3}</P>
    <SectionHead>{t.about_open}</SectionHead>
    <P>{t.about_p4}</P>
    <CompanyFooter text={t.about_footer} />
  </>
}

export function PrivacyContent() {
  const { t } = useLang()
  return <>
    <P style={{ fontStyle: 'italic' }}>{t.pp_lead}</P>

    <SectionHead>{t.pp_summary_h}</SectionHead>
    <P>{t.pp_summary_p1}</P>
    <P>{t.pp_summary_p2}</P>
    <P>{t.pp_summary_p3}</P>
    <P>{t.pp_summary_p4}</P>

    <SectionHead>{t.pp_scope_h}</SectionHead>
    <P>{t.pp_scope_p1}</P>
    <P>{t.pp_scope_p2}</P>

    <SectionHead>{t.pp_info_account_h}</SectionHead>
    <P>{t.pp_info_account_p1}</P>
    <P>{t.pp_info_account_p2}</P>
    <P>{t.pp_info_account_p3}</P>

    <SectionHead>{t.pp_info_camera_motion_h}</SectionHead>
    <P>{t.pp_info_camera_motion_p1}</P>
    <P>{t.pp_info_camera_motion_p2}</P>
    <P>{t.pp_info_camera_motion_p3}</P>

    <SectionHead>{t.pp_info_liveness_h}</SectionHead>
    <P>{t.pp_info_liveness_p1}</P>
    <P>{t.pp_info_liveness_p2}</P>

    <SectionHead>{t.pp_info_automatic_h}</SectionHead>
    <P>{t.pp_info_automatic_p1}</P>
    <P>{t.pp_info_automatic_p2}</P>
    <P>{t.pp_info_automatic_p3}</P>

    <SectionHead>{t.pp_info_cookies_h}</SectionHead>
    <P>{t.pp_info_cookies_p1}</P>
    <P>{t.pp_info_cookies_p2}</P>

    <SectionHead>{t.pp_how_we_use_h}</SectionHead>
    <P>{t.pp_how_we_use_p1}</P>
    <P>{t.pp_how_we_use_p2}</P>
    <P>{t.pp_how_we_use_p3}</P>
    <P>{t.pp_how_we_use_p4}</P>

    <SectionHead>{t.pp_model_training_h}</SectionHead>
    <P>{t.pp_model_training_p1}</P>
    <P>{t.pp_model_training_p2}</P>
    <P>{t.pp_model_training_p3}</P>
    <P>{t.pp_model_training_p4}</P>

    <SectionHead>{t.pp_biometric_h}</SectionHead>
    <P>{t.pp_biometric_p1}</P>
    <P>{t.pp_biometric_p2}</P>
    <P>{t.pp_biometric_p3}</P>
    <P>{t.pp_biometric_p4}</P>
    <P>{t.pp_biometric_p5}</P>
    <P>{t.pp_biometric_p6}</P>

    <SectionHead>{t.pp_retention_h}</SectionHead>
    <P>{t.pp_retention_p1}</P>
    <P>{t.pp_retention_p2}</P>
    <P>{t.pp_retention_p3}</P>

    <SectionHead>{t.pp_children_h}</SectionHead>
    <P>{t.pp_children_p1}</P>
    <P>{t.pp_children_p2}</P>
    <P>{t.pp_children_p3}</P>

    <SectionHead>{t.pp_your_rights_h}</SectionHead>
    <P>{t.pp_your_rights_p1}</P>
    <P>{t.pp_your_rights_p2}</P>

    <SectionHead>{t.pp_california_h}</SectionHead>
    <P>{t.pp_california_p1}</P>
    <P>{t.pp_california_p2}</P>
    <P>{t.pp_california_p3}</P>
    <P>{t.pp_california_p4}</P>
    <P>{t.pp_california_p5}</P>

    <SectionHead>{t.pp_other_states_h}</SectionHead>
    <P>{t.pp_other_states_p1}</P>
    <P>{t.pp_other_states_p2}</P>
    <P>{t.pp_other_states_p3}</P>

    <SectionHead>{t.pp_cookies_h}</SectionHead>
    <P>{t.pp_cookies_p1}</P>
    <P>{t.pp_cookies_p2}</P>

    <SectionHead>{t.pp_security_h}</SectionHead>
    <P>{t.pp_security_p1}</P>
    <P>{t.pp_security_p2}</P>

    <SectionHead>{t.pp_service_providers_h}</SectionHead>
    <P>{t.pp_service_providers_p1}</P>
    <P>{t.pp_service_providers_p2}</P>

    <SectionHead>{t.pp_international_h}</SectionHead>
    <P>{t.pp_international_p1}</P>
    <P>{t.pp_international_p2}</P>

    <SectionHead>{t.pp_changes_h}</SectionHead>
    <P>{t.pp_changes_p1}</P>
    <P>{t.pp_changes_p2}</P>

    <SectionHead>{t.pp_contact_h}</SectionHead>
    <P>{t.pp_contact_p1}</P>
    <P>{t.pp_contact_p2}</P>

    <div style={{ textAlign: 'center', marginTop: 10 }}>
      <div style={{ fontSize: 11, color: '#999' }}>{t.pp_footer}</div>
    </div>
  </>
}

export function TermsContent() {
  const { t } = useLang()
  return <>
    <P style={{ fontStyle: 'italic' }}>{t.tos_lead}</P>

    <SectionHead>{t.tos_intro_h}</SectionHead>
    <P>{t.tos_intro_p1}</P>
    <P>{t.tos_intro_p2}</P>

    <SectionHead>{t.tos_eligibility_h}</SectionHead>
    <P>{t.tos_eligibility_p1}</P>
    <P>{t.tos_eligibility_p2}</P>
    <P>{t.tos_eligibility_p3}</P>
    <P>{t.tos_eligibility_p4}</P>

    <SectionHead>{t.tos_what_cookcredit_is_h}</SectionHead>
    <P>{t.tos_what_cookcredit_is_p1}</P>
    <P>{t.tos_what_cookcredit_is_p2}</P>

    <SectionHead>{t.tos_account_h}</SectionHead>
    <P>{t.tos_account_p1}</P>
    <P>{t.tos_account_p2}</P>

    <SectionHead>{t.tos_assessment_scores_h}</SectionHead>
    <P>{t.tos_assessment_scores_p1}</P>
    <P>{t.tos_assessment_scores_p2}</P>
    <P>{t.tos_assessment_scores_p3}</P>

    <SectionHead>{t.tos_credits_h}</SectionHead>
    <P>{t.tos_credits_p1}</P>
    <P>{t.tos_credits_p2}</P>

    <SectionHead>{t.tos_marketplace_h}</SectionHead>
    <P>{t.tos_marketplace_p1}</P>
    <P>{t.tos_marketplace_p2}</P>
    <P>{t.tos_marketplace_p3}</P>

    <SectionHead>{t.tos_acceptable_use_h}</SectionHead>
    <P>{t.tos_acceptable_use_p1}</P>
    <P>{t.tos_acceptable_use_p2}</P>

    <SectionHead>{t.tos_user_content_license_h}</SectionHead>
    <P>{t.tos_user_content_license_p1}</P>
    <P>{t.tos_user_content_license_p2}</P>
    <P>{t.tos_user_content_license_p3}</P>
    <P>{t.tos_user_content_license_p4}</P>
    <P>{t.tos_user_content_license_p5}</P>

    <SectionHead>{t.tos_knife_safety_h}</SectionHead>
    <P>{t.tos_knife_safety_p1}</P>
    <P>{t.tos_knife_safety_p2}</P>

    <SectionHead>{t.tos_indemnification_h}</SectionHead>
    <P>{t.tos_indemnification_p1}</P>
    <P>{t.tos_indemnification_p2}</P>

    <SectionHead>{t.tos_intellectual_property_h}</SectionHead>
    <P>{t.tos_intellectual_property_p1}</P>
    <P>{t.tos_intellectual_property_p2}</P>

    <SectionHead>{t.tos_third_party_h}</SectionHead>
    <P>{t.tos_third_party_p1}</P>

    <SectionHead>{t.tos_disclaimers_h}</SectionHead>
    <P>{t.tos_disclaimers_p1}</P>
    <P>{t.tos_disclaimers_p2}</P>

    <SectionHead>{t.tos_limitation_liability_h}</SectionHead>
    <P>{t.tos_limitation_liability_p1}</P>
    <P>{t.tos_limitation_liability_p2}</P>

    <SectionHead>{t.tos_disputes_h}</SectionHead>
    <P>{t.tos_disputes_p1}</P>
    <P>{t.tos_disputes_p2}</P>
    <P>{t.tos_disputes_p3}</P>
    <P>{t.tos_disputes_p4}</P>
    <P>{t.tos_disputes_p5}</P>
    <P>{t.tos_disputes_p6}</P>

    <SectionHead>{t.tos_governing_law_h}</SectionHead>
    <P>{t.tos_governing_law_p1}</P>
    <P>{t.tos_governing_law_p2}</P>

    <SectionHead>{t.tos_termination_h}</SectionHead>
    <P>{t.tos_termination_p1}</P>
    <P>{t.tos_termination_p2}</P>

    <SectionHead>{t.tos_changes_h}</SectionHead>
    <P>{t.tos_changes_p1}</P>

    <SectionHead>{t.tos_contact_h}</SectionHead>
    <P>{t.tos_contact_p1}</P>

    <div style={{ textAlign: 'center', marginTop: 10 }}>
      <div style={{ fontSize: 11, color: '#999' }}>{t.tos_footer}</div>
    </div>
  </>
}

export function BiometricContent() {
  // Compact, faithful surface of legal/BIOMETRIC_NOTICE.md (the full BIPA §15(b) release).
  const { t } = useLang()
  return <>
    <P style={{ fontStyle: 'italic' }}>{t.bio_lead}</P>
    <SectionHead>{t.bio_collect_h}</SectionHead>
    <P>{t.bio_collect_p}</P>
    <SectionHead>{t.bio_why_h}</SectionHead>
    <P>{t.bio_why_p}</P>
    <SectionHead>{t.bio_keep_h}</SectionHead>
    <P>{t.bio_keep_p}</P>
    <SectionHead>{t.bio_sell_h}</SectionHead>
    <P>{t.bio_sell_p}</P>
    <SectionHead>{t.bio_choice_h}</SectionHead>
    <P>{t.bio_choice_p}</P>
    <SectionHead>{t.bio_age_h}</SectionHead>
    <P>{t.bio_age_p}</P>
    <SectionHead>{t.bio_states_h}</SectionHead>
    <P>{t.bio_states_p}</P>
    <P style={{ fontSize: 11, color: '#999', marginTop: 12 }}>{t.bio_draft}</P>
  </>
}

export function HelpContent() {
  const { t } = useLang()
  const faqs = [
    { q: t.help_q1, a: t.help_a1 },
    { q: t.help_q2, a: t.help_a2 },
    { q: t.help_q3, a: t.help_a3 },
    { q: t.help_q4, a: t.help_a4 },
    { q: t.help_q5, a: t.help_a5 },
  ]
  return <>
    {faqs.map((f, i) => (
      <div key={i} style={{
        background: '#fafafa', borderRadius: 0, borderLeft: '2px solid #e5e5e5', padding: '12px 14px', marginBottom: 10,
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', marginBottom: 3 }}>{f.q}</div>
        <div style={{ fontSize: 12, color: '#555', lineHeight: 1.5 }}>{f.a}</div>
      </div>
    ))}
    <button onClick={() => { window.location.href = 'mailto:connectwithus@cookcredit.com' }} style={{
      display: 'block', width: '100%', padding: 12, borderRadius: 0, marginTop: 16,
      background: '#1F6F5C', color: '#fff', textAlign: 'center',
      fontSize: 13, fontWeight: 600, border: 'none', cursor: 'pointer',
    }}>
      {t.help_contact}
    </button>
  </>
}
