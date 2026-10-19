import os
import shutil
import tempfile
from pathlib import Path

import pytest

os.environ["JOBOS_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")

from app import importers, latex, linkedin, warmpaths  # noqa: E402

ME = {"school": "UC Davis", "past_employers": ["Intuit"], "programs": ["ColorStack"], "hometown": "", "high_school": "",
      "weights": {"pastEmployer": 4, "program": 3, "university": 2, "hometown": 1}}


def test_company_matching():
    assert warmpaths.same_company("Stripe, Inc.", "stripe")
    assert warmpaths.same_company("Stripe Payments", "Stripe")
    assert warmpaths.same_company("Meta", "Facebook")
    assert not warmpaths.same_company("Metabase", "Meta")
    assert not warmpaths.same_company("", "Stripe")


def test_ranking_prefers_warm_reachable_people():
    job = {"company": "Stripe", "role": "Software Engineer, Payments"}
    people = [
        {"id": 1, "name": "VP", "company": "Stripe", "title": "VP Engineering", "degree": 2},
        {"id": 2, "name": "Alum", "company": "Stripe", "title": "Software Engineer", "degree": 1, "relationship": "UC Davis, ColorStack"},
        {"id": 3, "name": "Recruiter", "company": "Stripe", "title": "Technical Recruiter"},
        {"id": 4, "name": "Elsewhere", "company": "Plaid", "title": "Software Engineer", "degree": 1},
    ]
    ranked = warmpaths.rank_for_job(job, people, ME, {})
    assert [p["name"] for p in ranked] == ["Alum", "Recruiter", "VP"]
    assert "UC Davis alum" in ranked[0]["reasons"]
    assert warmpaths.coverage(ranked) == "strong"
    assert warmpaths.coverage([]) == "gap"


def test_inverted_u_tie_strength():
    s = warmpaths.TIE_STRENGTH_SCORE
    assert s[warmpaths.tie_strength(4)] > s[warmpaths.tie_strength(10)] > s[warmpaths.tie_strength(0)]


def test_linkedin_connections_csv():
    csv = ("Notes:\n\"When exporting your connection data, you may notice...\"\n\n"
           "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
           "Jane,Doe,https://www.linkedin.com/in/janedoe,,Stripe,Software Engineer,05 Mar 2026\n")
    [p] = importers.parse(csv, "connections")
    assert p["name"] == "Jane Doe" and p["company"] == "Stripe" and p["degree"] == 1
    assert p["connected_on"] == "2026-03-05"


def test_referral_sheet_csv():
    [p] = importers.parse("Name,Company,Notes\nSam Lee,Figma,Happy to refer new grads\n", "referral_sheet")
    assert p["source"] == "referral_sheet" and p["notes"] == "Happy to refer new grads"


def test_search_urls():
    url = linkedin.job_search_url("Software Engineer", "", "24h", True, ["remote"])
    assert "f_TPR=r86400" in url and "sortBy=DD" in url and "f_WT=2" in url
    searches = linkedin.people_searches({"company": "Stripe", "role": "Senior Software Engineer II"}, ME)
    assert "network=%5B%22F%22%5D" in searches[0]["url"]
    assert any("UC+Davis" in s["url"] for s in searches)
    assert linkedin.role_core("Senior Software Engineer II (Payments)") == "Software Engineer"


def test_url_key():
    from app.main import url_key
    assert url_key("https://www.linkedin.com/jobs/search/?currentJobId=42&x=1") == "linkedin.com/jobs/view/42"
    assert url_key("https://job-boards.greenhouse.io/stripe/jobs/123/application") == "job-boards.greenhouse.io/stripe/jobs/123"


RESUME = {
    "name": "Jane Doe",
    "contacts": ["Springfield, IL", "me@example.com", "linkedin.com/in/me"],
    "sections": [
        {"title": "Experience", "lines": [], "entries": [
            {"heading": "Intuit", "subheading": "SWE Intern", "date": "Summer 2026", "location": "Remote",
             "bullets": ["Cut p95 latency **40%** & shipped C# _stuff_ for 100% of users — fast"]}]},
        {"title": "Skills", "lines": ["**Languages:** Python, C++"], "entries": []},
    ],
}


def test_latex_escaping():
    tex = latex.render(RESUME)
    assert r"\textbf{40\%}" in tex and r"\&" in tex and r"\_stuff\_" in tex and "—" not in tex


@pytest.mark.skipif(not latex.compiler(), reason="no LaTeX compiler")
def test_latex_compiles(tmp_path, monkeypatch):
    monkeypatch.setattr(latex, "RESUMES", tmp_path)
    out = latex.compile_tex(latex.render(RESUME), {"id": 1, "company": "Stripe", "role": "SWE"}, {"name": "Jane Doe"})
    assert out["error"] is None, out["error"]
    assert out["pages"] == 1
    assert Path(out["pdf"]).name == "Jane_Doe_Resume_Stripe.pdf"
