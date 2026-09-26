"""
Server-of-record match engine — the authoritative scorer behind the B2B pipeline and the AEDT
audit trail. Faithful Python port of frontend/src/utils/match.js (the client runs the same logic
for an instant preview; THIS result is the one of record). Two stages:

  A. HARD GATES — bona-fide deal-breakers only (required cert, must-have skills, verified-skill
     floor). A gated candidate is auditable ("Does not meet: …"), never silently buried.
  B. REQUIREMENT COVERAGE — weighted coverage of required[] (child-satisfies-parent via the
     taxonomy) + a smaller preferred[] boost. Met/not-met only (NO keyword density). A technique
     requirement may be met by the camera-VERIFIED score, not just self-reported resume text.

Job-related key-points only (never name/age/school). Every score returns the inputs + named
weights so an AEDT row is fully reconstructable (NYC LL144 / EEOC four-fifths).
"""
from services.taxonomy import satisfies, label_of, BY_ID

VERIFIED_TECHNIQUE_THRESHOLD = 70   # a technique req can be met by a verified score at/above this
MATCH_POLICY_VERSION = "cookcredit-role-match-v1"

# Weights recorded into the audit log (mirror ROLE_WEIGHTS in ranking.js; the match TERM is one
# bounded input that never buys down the verified-skill anchor of the full composite rank).
FEATURE_WEIGHTS = {
    "skill": 0.45, "match": 0.12, "rating": 0.13, "proximity": 0.10,
    "cuisine": 0.05, "availability": 0.05, "experience": 0.05, "exposure": 0.05,
}


def _is_technique(node_id):
    n = BY_ID.get(node_id)
    return bool(n) and n["category"] == "technique"


def hard_gates(cook, role):
    """Stage A — hard gates plus items that require a person to review evidence."""
    failures = []
    manual_review = []
    points = cook.get("resumePoints") or []
    verified = cook.get("verifiedScore")
    assessment_eligible = bool(cook.get("assessmentEligible"))

    for cert_id in role.get("certsRequired") or []:
        if not any(satisfies(p, cert_id) for p in points):
            failures.append(f"Missing {label_of(cert_id)}")

    for skill_id in role.get("mustHave") or []:
        ok_resume = any(satisfies(p, skill_id) for p in points)
        ok_verified = (assessment_eligible and _is_technique(skill_id)
                       and (verified or 0) >= VERIFIED_TECHNIQUE_THRESHOLD)
        if not ok_resume and not ok_verified:
            if _is_technique(skill_id) and verified is not None and not assessment_eligible:
                manual_review.append(f"Review the shared {label_of(skill_id)} work sample")
            else:
                failures.append(f"Missing {label_of(skill_id)}")

    floor = role.get("skillFloor")
    if floor is not None:
        if not assessment_eligible and verified is not None:
            manual_review.append("Assessment threshold is disabled pending employment validation")
        elif (verified or 0) < floor:
            failures.append(f"Verified skill below {floor}")

    return {"passed": len(failures) == 0, "failures": failures,
            "manualReview": list(dict.fromkeys(manual_review))}


def requirement_match(cook, role):
    """Stage B — coverage of required + preferred, with per-requirement met/source."""
    points = cook.get("resumePoints") or []
    verified = cook.get("verifiedScore")
    assessment_eligible = bool(cook.get("assessmentEligible"))
    requirements = []

    def eval_one(req_id, kind):
        from_resume = any(satisfies(p, req_id) for p in points)
        from_verified = (assessment_eligible and _is_technique(req_id)
                         and (verified or 0) >= VERIFIED_TECHNIQUE_THRESHOLD)
        met = from_resume or from_verified
        requirements.append({
            "id": req_id, "label": label_of(req_id), "kind": kind,
            "status": "met" if met else "missing",
            "source": (f"verified {verified}" if from_verified else "resume" if from_resume else None),
        })
        return met

    required = role.get("required") or []
    preferred = role.get("preferred") or []
    req_met = sum(1 for r in required if eval_one(r, "required"))
    pref_met = sum(1 for p in preferred if eval_one(p, "preferred"))
    req_cov = (req_met / len(required)) if required else 1.0
    pref_cov = (pref_met / len(preferred)) if preferred else 0.0
    coverage = (0.8 * req_cov + 0.2 * pref_cov) if required else pref_cov
    coverage = max(0.0, min(1.0, coverage))
    return {
        "coverage": coverage, "reqMet": req_met, "reqTotal": len(required),
        "prefMet": pref_met, "prefTotal": len(preferred), "requirements": requirements,
    }


def match_role(cook, role):
    """Full match → bounded total + coarse band + explainable breakdown (the audit-of-record value)."""
    gates = hard_gates(cook, role)
    cov = requirement_match(cook, role)
    total = cov["coverage"] if gates["passed"] else 0.0
    band = ("Gated" if not gates["passed"]
            else "Strong fit" if total >= 0.85
            else "Qualified" if total >= 0.6
            else "Partial" if total > 0 else "Below")
    return {
        "total": round(total, 4), "percent": round(total * 100),
        "band": band, "gates": gates, **cov,
        "explanation": {
            "policyVersion": MATCH_POLICY_VERSION,
            "formula": ("If every stated hard requirement passes: 80% required-requirement "
                        "coverage plus 20% preferred-requirement coverage. If there are no "
                        "required requirements, the result is preferred coverage."),
            "hardGateEffect": "A failed hard requirement sets role match to 0; it is shown by name.",
            "verifiedTechniqueThreshold": VERIFIED_TECHNIQUE_THRESHOLD,
            "inputsUsed": ["role requirements", "shared verified assessment score",
                           "candidate-confirmed resume key points"],
            "inputsExcluded": ["name", "photo", "age", "school", "home address",
                               "race", "sex", "disability", "national origin"],
            "decision": "Decision support only. CookCredit does not make the hiring decision.",
            "assessmentEmploymentValidated": bool(cook.get("assessmentEligible")),
        },
    }
