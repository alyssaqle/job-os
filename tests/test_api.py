"""End-to-end through the HTTP API with Claude stubbed out (no API key, no cost)."""
import os
import tempfile
from pathlib import Path

os.environ["JOBOS_DB"] = str(Path(tempfile.mkdtemp()) / "api.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import ai, latex, main  # noqa: E402

client = TestClient(main.app)


def test_full_loop(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path)
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")  # never touch my real profile in tests
    monkeypatch.setattr(ai, "extract_job", lambda text: {"company": "Stripe", "role": "Software Engineer", "location": "SF", "url": "", "jd": "Build payments."})
    monkeypatch.setattr(ai, "tailor_resume", lambda job, note="": {"resume": {"name": "Me", "contacts": ["me@x.com"], "sections": []},
                                                          "changes": ["reordered"], "jd_keywords": [], "gaps_not_added": []})
    monkeypatch.setattr(ai, "extract_person", lambda text, url: {
        "name": "Jane Doe", "headline": "", "title": "Software Engineer", "company": "Stripe", "location": "",
        "degree": 2, "school": "", "past_companies": [], "shared": ""})
    monkeypatch.setattr(ai, "draft_message", lambda *a, **k: {"draft": "hey", "subject": "", "why_this_works": "short"})

    # 1. On a job page: save it from the page text, no pasting
    page = {"url": "https://www.linkedin.com/jobs/search/?currentJobId=99", "title": "SWE", "text": "job posting..."}
    job_id = client.post("/api/page/save-job", json=page).json()["id"]
    assert client.post("/api/page/save-job", json=page).json()["existing"]  # dedupes
    assert client.post("/api/page/job", json={"url": "https://www.linkedin.com/jobs/view/99/"}).json()["job"]["id"] == job_id

    # 2. Tailor -> PDF
    r = client.post(f"/api/jobs/{job_id}/tailor").json()
    if latex.compiler():
        assert r["pdf_url"] and client.get(r["pdf_url"]).status_code == 200

    # 3. Applied (auto-detected confirmation page)
    assert client.post("/api/track/applied", json={"job_id": job_id}).json()["company"] == "Stripe"
    assert client.get(f"/api/jobs/{job_id}").json()["job"]["status"] == "applied"

    # 4. Visit a LinkedIn profile -> matched to the Stripe job
    prof = client.post("/api/page/person", json={"url": "https://www.linkedin.com/in/janedoe/?x=1", "text": "Jane Doe ..."}).json()
    assert prof["person"]["name"] == "Jane Doe" and prof["jobs"][0]["job"]["id"] == job_id

    # 5. Clicked Connect on LinkedIn -> logged automatically
    assert client.post("/api/track/outreach", json={"linkedin_url": "https://www.linkedin.com/in/janedoe", "kind": "requested"}).json()["ok"]
    nu = client.get("/api/nextup").json()
    assert not any(i["kind"] == "reach_out" and i["job_id"] == job_id for i in nu)

    # 6. They accepted (profile now says 1st) -> Next Up says send the pitch
    monkeypatch.setattr(ai, "extract_person", lambda text, url: {
        "name": "Jane Doe", "headline": "", "title": "Software Engineer", "company": "Stripe", "location": "",
        "degree": 1, "school": "", "past_companies": [], "shared": ""})
    client.post("/api/page/person", json={"url": "https://www.linkedin.com/in/janedoe", "text": "Jane Doe 1st"})
    assert any("accepted" in i["title"] for i in client.get("/api/nextup").json())

    # 7. Message sent -> job moves to reached_out, follow-up scheduled
    pid = prof["person"]["id"]
    client.put(f"/api/jobs/{job_id}/people/{pid}", json={"status": "messaged", "message": "hey"})
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["job"]["status"] == "reached_out"
    assert detail["people"][0]["link"]["follow_up_on"]

    board = client.get("/api/jobs").json()
    assert board[0]["contacted"] == 1


def test_resume_chat(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    job_id = client.post("/api/jobs", json={"company": "Acme", "role": "Marketing Analyst", "jd": "SQL, campaigns"}).json()["id"]

    seen = {}

    def fake_chat(job, transcript, message, current, own_tex, note=""):
        seen["transcript"] = transcript
        return {"reply": "Did you work with marketing at Intuit?", "questions": [], "new_facts": ["Intern @ Intuit: built campaign dashboard"],
                "update_resume": bool(message), "changes": [],
                "resume": {"name": "Me", "contacts": [], "sections": []}}

    monkeypatch.setattr(ai, "resume_chat", fake_chat)
    first = client.post(f"/api/jobs/{job_id}/resume-chat", json={"message": ""}).json()
    assert not first["updated"]
    second = client.post(f"/api/jobs/{job_id}/resume-chat", json={"message": "yes, a campaign dashboard"}).json()
    assert second["updated"]
    assert [m["role"] for m in seen["transcript"]] == ["claude"]
    assert [m["role"] for m in client.get(f"/api/jobs/{job_id}/resume-chat").json()] == ["claude", "me", "claude"]

    client.post(f"/api/jobs/{job_id}/save-facts", json={"facts": second["new_facts"]})
    saved = (tmp_path / "profile" / "experience.md").read_text()
    assert "built campaign dashboard" in saved and "Marketing Analyst @ Acme" in saved


def test_two_versions(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    profile.save_me({"name": "Jane Doe", "single_version_companies": ["Google"],
                     "variants": {"A": {"name": "Jane Doe", "email": "a@example.com", "strategy": "product"},
                                  "B": {"name": "Janie Q Doe", "email": "b@example.com", "strategy": "data"}}})
    notes = []

    def fake_tailor(job, note=""):
        notes.append(note)
        return {"resume": {"name": "Jane Doe", "contacts": ["someone@example.com"], "sections": []},
                "changes": [], "jd_keywords": [], "gaps_not_added": []}

    monkeypatch.setattr(ai, "tailor_resume", fake_tailor)
    jid = client.post("/api/jobs", json={"company": "Stripe", "role": "Data Analyst"}).json()["id"]
    a = client.post(f"/api/jobs/{jid}/tailor?variant=A").json()
    b = client.post(f"/api/jobs/{jid}/tailor?variant=B").json()
    assert "VERSION A" in notes[0] and "VERSION B" in notes[1] and "b@example.com" in notes[1]

    detail = client.get(f"/api/jobs/{jid}").json()
    assert "a@example.com" in detail["job"]["tailored_resume"] and "someone@" not in detail["job"]["tailored_resume"]
    assert "b@example.com" in detail["job"]["tailored_resume_b"]
    assert "Janie Q Doe" in detail["job"]["tailored_resume_b"] and "Jane Doe" not in detail["job"]["tailored_resume_b"]
    assert detail["variants"]["B"]["filename"] == "Janie_Q_Doe_Resume_Stripe.pdf"
    if latex.compiler():
        assert a["pdf_url"] != b["pdf_url"] and client.get(b["pdf_url"]).status_code == 200

    google = client.post("/api/jobs", json={"company": "Google LLC", "role": "Analyst"}).json()["id"]
    assert client.post(f"/api/jobs/{google}/tailor?variant=B").status_code == 400

    client.post("/api/track/applied", json={"job_id": jid, "variants": ["A", "B"]})
    client.patch(f"/api/jobs/{jid}", json={"response_variant": "B"})
    stats = client.get("/api/ab-stats").json()
    assert stats["B"]["replies"] == 1 and stats["A"]["replies"] == 0 and stats["A"]["sent"] == 1


def test_draft_options_pass_through(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    got = {}

    def fake_draft(job, person, kind, personalization="", tier=1, previous="", language="en", not_open=False):
        got.update(kind=kind, language=language, not_open=not_open)
        return {"draft": "hi", "subject": "", "why_this_works": ""}

    monkeypatch.setattr(ai, "draft_message", fake_draft)
    jid = client.post("/api/jobs", json={"company": "FOX", "role": "PM Intern"}).json()["id"]
    pid = client.post(f"/api/jobs/{jid}/people", json={"name": "Sam Lee", "title": "Incoming PM Intern"}).json()["id"]
    r = client.post(f"/api/jobs/{jid}/people/{pid}/draft", json={"kind": "peer_congrats", "language": "es", "not_open": True})
    assert r.status_code == 200 and got == {"kind": "peer_congrats", "language": "es", "not_open": True}


def test_message_kinds_format():
    for k, v in ai.KINDS.items():
        v.format(limit=200, tier=1, tier_guidance="", calendly_hint="x", calendly_line="y", school="State U", first_name="Jane")
    assert list(ai.KINDS)[:3] == ["peer_congrats", "alumni", "connected_pitch"]


def test_voice_memory(tmp_path, monkeypatch):
    from app import profile
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    profile.write("voice", "# My Voice\nwarm")
    client.post("/api/voice/note", json={"text": "fewer emojis with directors"})
    for i in range(20):
        profile.remember_sent(f"Hey! message number {i} that I really sent", "test")
    text = profile.read("voice")[0]
    assert text.startswith("# My Voice\nwarm") and "fewer emojis with directors" in text
    assert "number 19" in text and "number 4 " not in text  # keeps only the latest 15


def test_auto_fit_one_page(monkeypatch, tmp_path):
    import pytest
    if not latex.compiler():
        pytest.skip("no LaTeX compiler")
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    long = {"name": "Me", "contacts": [], "sections": [{"title": "Experience", "lines": [], "entries": [
        {"heading": f"Co {i}", "subheading": "Role", "date": "2025", "location": "", "bullets": ["Did a thing " * 20] * 4}
        for i in range(8)]}]}
    monkeypatch.setattr(ai, "tailor_resume", lambda job, note="": {"resume": long, "changes": [], "jd_keywords": [], "gaps_not_added": []})
    calls = []

    def fake_fit(tex, pages, job, attempt):
        calls.append(pages)
        short = dict(long, sections=[{"title": "Experience", "lines": [], "entries": long["sections"][0]["entries"][:2]}])
        return {"tex": latex.render(short), "cut": ["dropped 6 roles"]}

    monkeypatch.setattr(ai, "fit_one_page", fake_fit)
    jid = client.post("/api/jobs", json={"company": "Bosch", "role": "Intern"}).json()["id"]
    r = client.post(f"/api/jobs/{jid}/tailor").json()
    assert calls and calls[0] > 1 and r["pages"] == 1 and r["cut_to_fit"] == ["dropped 6 roles"]


def test_picks_and_score(monkeypatch, tmp_path):
    import json as _json
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    jid = client.post("/api/jobs", json={"company": "Bosch", "role": "AI Intern", "jd": "Excel, SAP, Python"}).json()["id"]
    with main.db.session() as conn:
        conn.execute("UPDATE jobs SET fit_notes = ? WHERE id = ?",
                     (_json.dumps({"jd_keywords": ["Python", "SAP"], "experience_ranking": []}), jid))
    seen = {}

    def fake_chat(job, transcript, message, current, own_tex, note=""):
        seen["msg"] = message
        return {"reply": "done", "questions": [], "new_facts": [], "update_resume": True, "changes": [],
                "resume": {"name": "Me", "contacts": [], "sections": [{"title": "Skills", "lines": ["Python, Excel"], "entries": []}]}}

    monkeypatch.setattr(ai, "resume_chat", fake_chat)
    r = client.post(f"/api/jobs/{jid}/rebuild-with-picks", json={
        "variant": "A", "base_version": "Version H: AI Product / PM",
        "picks": [{"experience": "Acme Corp", "include": True, "how": "lead with Copilot"},
                  {"experience": "Old Project", "include": False, "how": ""}],
        "note": "no GPA"}).json()
    assert "Acme Corp -> lead with Copilot" in seen["msg"] and "REMOVE completely: Old Project" in seen["msg"]
    assert "Version H" in seen["msg"] and "no GPA" in seen["msg"]
    assert r["score"] == {"score": 50, "matched": ["Python"], "missing": ["SAP"]}


def test_stretch_skills_learn_list(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(ai, "tailor_resume", lambda job, note="": {
        "resume": {"name": "Me", "contacts": [], "sections": []}, "changes": [], "jd_keywords": ["Power BI"],
        "gaps_not_added": [], "stretch_skills": ["Power BI", "AWS"]})
    jid = client.post("/api/jobs", json={"company": "Acme Analytics", "role": "Product Analyst", "jd": "Power BI"}).json()["id"]
    client.post(f"/api/jobs/{jid}/tailor")
    assert client.get(f"/api/jobs/{jid}").json()["job"]["stretch_skills"] == ["Power BI", "AWS"]
    client.post("/api/track/applied", json={"job_id": jid})
    learn = [i for i in client.get("/api/nextup").json() if i["kind"] == "learn" and i["job_id"] == jid]
    assert learn and "Power BI" in learn[0]["title"]


def test_cert_in_progress_is_a_todo(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(ai, "tailor_resume", lambda job, note="": {
        "resume": {"name": "Me", "contacts": [], "sections": []}, "changes": [], "jd_keywords": [],
        "gaps_not_added": [], "stretch_skills": [], "certs_to_start": ["AWS Cloud Practitioner"]})
    jid = client.post("/api/jobs", json={"company": "CloudCo", "role": "Technical PM Intern"}).json()["id"]
    client.post(f"/api/jobs/{jid}/tailor")
    todo = [i for i in client.get("/api/nextup").json() if i["job_id"] == jid and i["kind"] == "learn"]
    assert todo and todo[0]["title"].startswith("Start AWS Cloud Practitioner before applying")


def test_company_cert_rule(monkeypatch, tmp_path):
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    profile.save_me({"company_certs": {"Robinhood": ["FinTech Industry Professional (FTIP®) Certification"]}})
    seen = {}

    def fake(job, note=""):
        seen["block"] = ai._job_block(job)
        return {"resume": {"name": "Me", "contacts": [], "sections": []}, "changes": [], "jd_keywords": [],
                "gaps_not_added": [], "stretch_skills": [], "certs_to_start": []}

    monkeypatch.setattr(ai, "tailor_resume", fake)
    jid = client.post("/api/jobs", json={"company": "Robinhood Markets, Inc.", "role": "PM Intern"}).json()["id"]
    client.post(f"/api/jobs/{jid}/tailor")
    assert "FTIP" in seen["block"] and "(in progress)" in seen["block"]
    todo = [i for i in client.get("/api/nextup").json() if i["job_id"] == jid and i["kind"] == "learn"]
    assert todo and "FTIP" in todo[0]["title"]


def test_openai_writes_claude_does_latex(monkeypatch, tmp_path):
    """JOBOS_WRITER=openai: wording goes to OpenAI, LaTeX/technical stays on Claude."""
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    (tmp_path / "profile").mkdir(parents=True, exist_ok=True)
    (tmp_path / "profile" / "resume.tex").write_text("\\documentclass{article}\\begin{document}OLD\\end{document}")
    profile.write("resume", "# master resume")
    monkeypatch.setattr(ai, "WRITER", "openai")
    calls = []

    def fake_openai(prompt, schema, effort, max_tokens):
        calls.append(("openai", list(schema["properties"])))
        return {"resume": {"name": "Me", "contacts": [], "sections": []}, "changes": ["openai wrote this"],
                "jd_keywords": [], "gaps_not_added": [], "stretch_skills": [], "certs_to_start": []}

    def fake_claude_stream(*a, **k):
        raise AssertionError("Claude must not be asked to write resume wording")

    monkeypatch.setattr(ai, "_call_openai", fake_openai)
    monkeypatch.setattr(ai, "content_to_tex", lambda base, resume, job: (calls.append(("claude", "tex")) or
                        {"tex": "\\documentclass{article}\\begin{document}NEW\\end{document}"}))
    monkeypatch.setattr(ai.client().beta.messages, "stream", fake_claude_stream, raising=False)
    jid = client.post("/api/jobs", json={"company": "Stripe", "role": "PM Intern", "jd": "x"}).json()["id"]
    r = client.post(f"/api/jobs/{jid}/tailor").json()
    assert [c[0] for c in calls] == ["openai", "claude"] and "resume" in calls[0][1]
    assert r["changes"] == ["openai wrote this"]
    assert "NEW" in client.get(f"/api/jobs/{jid}").json()["job"]["tailored_resume"]


def test_fill_lines_keeps_only_improvements(monkeypatch, tmp_path):
    import pytest
    if not latex.compiler():
        pytest.skip("no LaTeX compiler")
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(ai, "tailor_resume", lambda job, note="": {
        "resume": {"name": "Me", "contacts": [], "sections": []}, "changes": [], "jd_keywords": [],
        "gaps_not_added": [], "stretch_skills": [], "certs_to_start": []})
    issue = {"line": "x", "previous": "y", "fill": 0.1}
    # 3 short lines -> pass 1 gets it to 1 (kept) -> pass 2 doesn't improve (reverted)
    reports = iter([[issue] * 3, [issue], [issue]])
    monkeypatch.setattr(latex, "short_lines", lambda pdf: next(reports, []))
    monkeypatch.setattr(ai, "fill_lines", lambda tex, issues, job: {"tex": tex.replace("Me", "Me "), "changed": ["tightened 2 bullets"]})
    jid = client.post("/api/jobs", json={"company": "Acme", "role": "PM"}).json()["id"]
    r = client.post(f"/api/jobs/{jid}/tailor").json()
    assert r["filled_lines"] == ["tightened 2 bullets"] and r["pages"] == 1


def test_fill_page_adds_content_only_if_still_one_page(monkeypatch, tmp_path):
    import pytest
    if not latex.compiler():
        pytest.skip("no LaTeX compiler")
    from app import profile
    monkeypatch.setattr(latex, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(profile, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(ai, "tailor_resume", lambda job, note="": {
        "resume": {"name": "Me", "contacts": [], "sections": []}, "changes": [], "jd_keywords": [],
        "gaps_not_added": [], "stretch_skills": [], "certs_to_start": []})
    space = iter([4.0, 1.0, 1.0])
    monkeypatch.setattr(latex, "free_lines", lambda pdf: next(space, 0.0))
    monkeypatch.setattr(ai, "add_content", lambda tex, free, job: {"tex": tex.replace("Me", "Me "), "added": ["side project"]})
    jid = client.post("/api/jobs", json={"company": "Epic", "role": "PM"}).json()["id"]
    r = client.post(f"/api/jobs/{jid}/tailor").json()
    assert r["filled_lines"] == ["Added: side project"] and r["pages"] == 1
