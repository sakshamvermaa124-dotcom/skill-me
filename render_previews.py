"""Render every email template to preview_emails/ with realistic sample data.

Usage (from the repo root):  python render_previews.py
Open the generated preview_emails/preview_*.html files in a browser to review them.
"""
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

template_dir = os.path.join("backend", "templates", "emails")
output_dir = "preview_emails"
os.makedirs(output_dir, exist_ok=True)

# Same settings as backend/services/email_service.py
env = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape(["html"]))

common = {
    "first_name": "Saksham",
    "last_name": "Verma",
    "email": "saksham@example.com",
    "domain_label": "Full Stack Engineer",
    "frontend_url": "https://skill-me-intern.in",
    "dashboard_url": "https://skill-me-intern.in/dashboard.html",
}

templates = {
    "application_received.html": {},
    "shortlisted.html": {},
    "offer_letter.html": {"joining_date": "16 August 2026"},
    "certificate_ready.html": {
        "cert_id": "SM-A1B2-C3D4-E5F6",
        "issued_date": "14 September 2026",
        "certificate_url": "https://skill-me-intern.in/certificate.html?email=saksham@example.com",
        "lor_url": "https://skill-me-intern.in/lor.html?cert_id=SM-A1B2-C3D4-E5F6",
        "verify_url": "https://skill-me-intern.in/verify.html?cert_id=SM-A1B2-C3D4-E5F6",
    },
    "submission_feedback.html": {
        "week": 2,
        "task_title": "Core Features",
        "checklist": [
            "Post shows the working feature (screenshot or short demo)",
            "Project link is in the post or its first comment",
            "@SkillMe is tagged",
        ],
    },
    "task_approved.html": {"week": 2, "score": 100, "admin_note": "Clean UI and a clear demo — great job."},
    "task_reminder.html": {"week_due": 3, "days_inactive": 6, "completed_tasks": 2},
    "urgent_request_fulfilled.html": {"request_type": "certificate"},
    "submission_flow_update.html": {},
}

for name, extra in templates.items():
    html = env.get_template(name).render(**common, **extra)
    path = os.path.join(output_dir, f"preview_{name}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated preview: {path}")

print(f"All {len(templates)} previews generated in {output_dir}/")
