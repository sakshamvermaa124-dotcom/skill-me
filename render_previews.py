import os
from jinja2 import Environment, FileSystemLoader

template_dir = os.path.join("backend", "templates", "emails")
output_dir = "preview_emails"

env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)

# Common mock data
mock_data = {
    "first_name": "Saksham",
    "last_name": "Verma",
    "email": "saksham@example.com",
    "domain_label": "Web Development",
    "github_username": "saksham124",
    "batch_number": 42,
    "joining_date": "10 August 2026",
    "repo_url": "https://github.com/skillme-interns/web-dev-batch-42",
    "frontend_url": "https://skill-me-intern.in",
    "dashboard_url": "https://skill-me-intern.in/dashboard.html",
    "certificate_url": "https://skill-me-intern.in/certificate.html?email=saksham@example.com",
    "verify_url": "https://skill-me-intern.in/certificate.html?cert_id=SKM-WEB-12345",
    "cert_id": "SKM-WEB-12345",
    "issued_date": "10 September 2026",
    "week_number": 1,
    "deadline": "17 August 2026",
    "task_count": 3,
    "tasks": [
        {"title": "Setup project structure and initialize Git", "issue_url": "https://github.com/skillme-interns/web-dev-batch-42/issues/1"},
        {"title": "Build responsive navigation bar", "issue_url": "https://github.com/skillme-interns/web-dev-batch-42/issues/2"},
        {"title": "Implement light/dark theme toggle", "issue_url": "https://github.com/skillme-interns/web-dev-batch-42/issues/3"}
    ]
}

templates = [
    "application_received.html",
    "shortlisted.html",
    "offer_letter.html",
    "weekly_tasks.html",
    "certificate_ready.html"
]

for tpl_name in templates:
    template = env.get_template(tpl_name)
    rendered_html = template.render(**mock_data)
    
    output_path = os.path.join(output_dir, f"preview_{tpl_name}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    print(f"Generated preview: {output_path}")

print("All previews generated successfully in the preview_emails/ directory.")
