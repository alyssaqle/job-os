import pytest

from app.workauth import check


@pytest.mark.parametrize("text", [
    "Applicants must be U.S. citizens.",
    "US citizenship required for this role.",
    "Must be a U.S. citizen or lawful permanent resident.",
    "Candidates must hold a green card.",
    "Must be authorized to work in the United States on a permanent basis without sponsorship.",
    "You must be legally authorized to work in the US indefinitely.",
    "We are unable to consider candidates on OPT or CPT.",
    "This role does not support F-1 student visas.",
    "OPT candidates are not eligible for this position.",
    "Active Secret security clearance required.",
    "Must be a U.S. person as defined by ITAR.",
    "- Indefinite U.S.\nwork authorized individuals only.\nFuture sponsorship for work authorization unavailable.",  # Bosch, verbatim
    "Permanent work authorization in the US is required.",
])
def test_dont_apply(text):
    r = check("We build great products.\n" + text + "\nBenefits: health.")
    assert r["verdict"] == "dont_apply", r
    assert r["quote"]


@pytest.mark.parametrize("text", [
    "We do not sponsor H-1B visas.",
    "Visa sponsorship is not available for this position.",
    "This company will not sponsor applicants for work visa status.",
    "Must be authorized to work in the U.S. without sponsorship now or in the future.",
])
def test_no_sponsorship_still_apply(text):
    r = check(text)
    assert r["verdict"] == "apply" and "Still apply" in r["reason"], r


def test_eeo_boilerplate_is_ignored():
    r = check("We consider all applicants regardless of race, religion, citizenship status, or national origin. "
              "Equal opportunity employer; qualified applicants will not be discriminated against based on citizenship.")
    assert r["verdict"] == "apply"


def test_silent_and_empty():
    assert check("Build dashboards in SQL and Tableau.")["verdict"] == "apply"
    assert check("")["verdict"] == "unknown"


@pytest.mark.parametrize("text", [
    "Must be a US citizen, permanent resident, or have any valid work authorization; OPT welcome.",
    "H-1B and green card sponsorship available for this role.",
    "We will sponsor visas, including for F-1 OPT students.",
])
def test_positive_context_is_not_blocked(text):
    assert check(text)["verdict"] == "apply"
