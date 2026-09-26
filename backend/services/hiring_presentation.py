"""Employer-authored presentation only; never affects measurements or matching."""
DEFAULT_INSTRUCTIONS = 'Keep your knife hand, blade and cutting board in view. Record 20–60 seconds at your normal, safe pace. Review your recording, then submit it to this application.'


def assessment_instructions(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 1500:
        raise ValueError('Assessment instructions must be text of at most 1500 characters')
    return value.strip() or None


def session_presentation(session, application):
    from models import RolePosting, Org, User, PartnerInvitation
    role = session.get(RolePosting, application.role_posting_id)
    org = session.get(Org, role.org_id) if role else None
    user = session.get(User, application.applicant_id)
    invitation = session.query(PartnerInvitation).filter_by(application_id=application.id).first()
    config = (invitation.request_config or {}) if invitation else ((role.requirements or {}) if role else {})
    return {
        'companyName': org.name if org else 'Your employer',
        'logoUrl': org.brand_logo_url if org else None,
        'roleTitle': role.title if role else 'Knife skills assessment',
        'instructions': config.get('assessmentInstructions') or DEFAULT_INSTRUCTIONS,
        'applicantName': (application.applicant_details or {}).get('name') or ((user.name or '') if user else ''),
    }
