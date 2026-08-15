"""
Unit & Integration Tests — Email Lifecycle Templates
Verifies HTML rendering, personalization, share intents, LinkedIn company links, and copy hygiene (no batch/open-source leaks).
"""
import pytest
from services.email_service import _render, _domain_label, email_service


class TestEmailTemplatesRendering:
    """Test individual Jinja2 template renders and verify their content structure."""

    def test_base_template_brand_and_footer(self):
        """base.html should render valid HTML with official LinkedIn link and no open-source subtitle."""
        html = _render(
            "application_received.html",
            first_name="Saksham",
            last_name="Verma",
            email="saksham@example.com",
            domain_label="Full-Stack Web Development",
            github_username="sakshamverma124",
        )
        assert "SkillMe" in html
        assert "https://www.linkedin.com/company/skill-me-intern/" in html
        assert "Technical Internship Program" in html
        # Ensure 'Open-Source Technical Program' has been cleaned from base subtitle
        assert "Open-Source Technical Program" not in html
        assert "Production Open Source" not in html

    def test_offer_letter_template_personalization_and_shares(self):
        """offer_letter.html must contain personalized offer URL, share intents, company page button, and no batch row."""
        html = _render(
            "offer_letter.html",
            first_name="Saksham",
            last_name="Verma",
            domain_label="Web Development Engineering",
            joining_date="16 August 2026",
            batch_number=1,
            repo_url="https://github.com/skill-me/web-dev-1",
            issues_url="https://github.com/skill-me/web-dev-1/issues?assignee=sakshamverma124",
            github_username="sakshamverma124",
            dashboard_url="https://skill-me-intern.in/dashboard.html",
        )
        # Personalized Greeting & Candidate Name
        assert "Dear Saksham," in html
        assert "Saksham Verma" in html
        assert "Web Development Engineering" in html

        # Hero Action Card & Online Offer Viewer
        assert "OFFICIAL APPOINTMENT DOCUMENT" in html
        assert "offer.html?name=Saksham+Verma" in html

        # Institutional HOD / NOC Verification Box
        assert "Need College NOC / HOD Verification?" in html
        assert "Official HOD Acceptance Letter" in html
        assert "4-Week Structured Work Syllabus" in html
        assert "Academic Evaluation Rubric" in html

        # 1-Click LinkedIn Post with personalized offer URL
        assert "https://www.linkedin.com/feed/?shareActive=true" in html
        assert "offer.html" in html
        assert "Saksham" in html

        # 1-Click WhatsApp Share
        assert "https://api.whatsapp.com/send?text=" in html

        # Dedicated 1-Click Button for SkillMe Company Page
        assert "btn-email-follow-company" in html
        assert "https://www.linkedin.com/company/skill-me-intern/" in html

        # Verify copy hygiene: no batch row in the summary table
        assert '<span class="info-label">Cohort Batch</span>' not in html
        assert "Batch #1" not in html
        assert "Open Source" not in html

    def test_application_received_template(self):
        """application_received.html renders screening steps and LinkedIn link."""
        html = _render(
            "application_received.html",
            first_name="Priya",
            last_name="Sharma",
            email="priya@example.com",
            domain_label="Python and AI Engineering",
            github_username="priyasharma",
        )
        assert "Priya" in html
        assert "Python and AI Engineering" in html
        assert "@priyasharma" in html
        assert "https://www.linkedin.com/company/skill-me-intern/" in html
        assert "Batch Allocation" not in html
        assert "open-source readiness" not in html

    def test_shortlisted_template(self):
        """shortlisted.html renders congratulations and clean sprint milestones."""
        html = _render(
            "shortlisted.html",
            first_name="Rahul",
            last_name="Nair",
            domain_label="DevOps and Cloud Engineering",
        )
        assert "Rahul" in html
        assert "DevOps and Cloud Engineering" in html
        assert "https://www.linkedin.com/company/skill-me-intern/" in html
        assert "batch schedule" not in html

    def test_weekly_tasks_template(self):
        """weekly_tasks.html renders sprint overview and issue links."""
        sample_tasks = [
            {"title": "Implement JWT Auth Middleware", "issue_url": "https://github.com/repo/issues/1"},
            {"title": "Add Rate Limiting to /api/v1", "issue_url": "https://github.com/repo/issues/2"},
        ]
        html = _render(
            "weekly_tasks.html",
            first_name="Ananya",
            last_name="Patel",
            domain_label="Web Development",
            week_number=1,
            task_count=2,
            deadline="23 August 2026",
            tasks=sample_tasks,
            issues_url="https://github.com/repo/issues",
            repo_url="https://github.com/repo",
        )
        assert "Ananya" in html
        assert "Week 1 of 4" in html
        assert "Implement JWT Auth Middleware" in html
        assert "Add Rate Limiting to /api/v1" in html
        assert "Batch #" not in html
        assert "Assigned Cohort Tasks" not in html

    def test_certificate_ready_template(self):
        """certificate_ready.html renders credential ID and verification link."""
        html = _render(
            "certificate_ready.html",
            first_name="Saksham",
            last_name="Verma",
            domain_label="Web Development",
            cert_id="SM-A1B2-C3D4-E5F6",
            issued_date="16 August 2026",
            certificate_url="https://skill-me-intern.in/certificate.html?cert_id=SM-A1B2-C3D4-E5F6",
            lor_url="https://skill-me-intern.in/lor.html?cert_id=SM-A1B2-C3D4-E5F6",
            verify_url="https://skill-me-intern.in/verify.html?cert_id=SM-A1B2-C3D4-E5F6",
        )
        assert "SM-A1B2-C3D4-E5F6" in html
        assert "Saksham Verma" in html
        assert "Web Development" in html
        assert "https://skill-me-intern.in/certificate.html" in html
        assert '<span class="info-label">Cohort Batch</span>' not in html


@pytest.mark.asyncio
class TestEmailServiceDispatch:
    """Test email service dispatch methods with mocked transport."""

    async def test_send_offer_letter_dispatch(self, monkeypatch):
        """send_offer_letter should build correct subject and deliver successfully."""
        sent_payloads = []

        async def mock_send_and_log(to_email, to_name, subject, html_content, email_type):
            sent_payloads.append({
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
                "email_type": email_type,
            })
            return True

        monkeypatch.setattr("services.email_service._send_and_log", mock_send_and_log)

        success = await email_service.send_offer_letter(
            first_name="Dev",
            last_name="Kapoor",
            email="dev@example.com",
            domain="web-dev",
            batch_number=1,
            github_username="devkapoor",
            repo_url="https://github.com/skill-me/web-dev-1",
        )

        assert success is True
        assert len(sent_payloads) == 1
        payload = sent_payloads[0]
        assert payload["to_email"] == "dev@example.com"
        assert payload["email_type"] == "offer_letter"
        assert "Batch #" not in payload["subject"]
        assert "Offer Letter" in payload["subject"]
        assert "Dev Kapoor" in payload["html_content"]
