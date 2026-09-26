"""Employment screening remains explainable and conservative before validation."""
from services.matching import match_role


def test_unvalidated_assessment_never_satisfies_or_gates_employment_requirement():
    result = match_role(
        {"verifiedScore": 92, "assessmentEligible": False, "resumePoints": []},
        {"mustHave": ["knife_skills"], "required": ["knife_skills"],
         "preferred": [], "skillFloor": 80, "certsRequired": []},
    )
    assert result["gates"]["passed"] is True
    assert result["gates"]["failures"] == []
    assert "Assessment threshold is disabled pending employment validation" in result["gates"]["manualReview"]
    assert result["requirements"][0]["status"] == "missing"
    assert result["requirements"][0]["source"] is None
    assert result["explanation"]["assessmentEmploymentValidated"] is False
    assert result["explanation"]["decision"].startswith("Decision support only")


def test_validated_assessment_use_is_still_fully_explained():
    result = match_role(
        {"verifiedScore": 92, "assessmentEligible": True, "resumePoints": []},
        {"mustHave": ["knife_skills"], "required": ["knife_skills"],
         "preferred": [], "skillFloor": 80, "certsRequired": []},
    )
    assert result["gates"] == {"passed": True, "failures": [], "manualReview": []}
    assert result["percent"] == 80
    assert result["requirements"][0]["source"] == "verified 92"
    assert result["explanation"]["formula"].startswith("If every stated hard requirement")
    assert "age" in result["explanation"]["inputsExcluded"]


def test_resume_evidence_does_not_need_assessment_validation():
    result = match_role(
        {"verifiedScore": 20, "assessmentEligible": False, "resumePoints": ["knife_skills"]},
        {"mustHave": ["knife_skills"], "required": ["knife_skills"],
         "preferred": [], "skillFloor": None, "certsRequired": []},
    )
    assert result["requirements"][0]["status"] == "met"
    assert result["requirements"][0]["source"] == "resume"
