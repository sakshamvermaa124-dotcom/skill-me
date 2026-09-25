"""
SkillMe — Automatic Submission Feedback
Builds the feedback a student receives when they submit a week's task: a checklist
drawn from that week's deliverables in their own project, a tip for the week's stage,
tips for their domain, and general tips that apply to every submission.

It is generated at submission time — before a reviewer has looked at the work — so it is
phrased as a checklist and suggestions and never claims anything about what the student did.
"""

from services.project_curriculum import get_project_track_for_student, resolve_domain_key

STAGE_TIPS = {
    1: "Week 1 is the foundation everything else builds on. Keep a clean folder structure and a README with setup steps now — it saves you time in weeks 2–4.",
    2: "Week 2 builds on week 1. Re-test your week 1 features after adding the new ones so nothing broke along the way.",
    3: "Week 3 is where projects start to feel real. Check how your work handles bad input, empty states and errors, not just the happy path.",
    4: "Week 4 is about finishing well. Do a full end-to-end run, remove leftover debug code, and update your README with final screenshots.",
}

DOMAIN_TIPS = {
    "web-dev": [
        "Check your layout at mobile (360px), tablet (768px) and desktop widths — horizontal scrolling is the most common issue.",
        "Run a Lighthouse audit in Chrome DevTools and fix anything below 90 in Accessibility.",
    ],
    "react": [
        "Keep components small and focused; move repeated logic into custom hooks.",
        "Open the browser console while using your app — clear any key or dependency-array warnings.",
    ],
    "node": [
        "Return proper HTTP status codes (400 for bad input, 404 for missing, 500 for server errors) with a clear JSON message.",
        "Keep secrets in a .env file and add .env to .gitignore before pushing.",
    ],
    "python": [
        "Add type hints and docstrings to your main functions — it makes your code much easier to review.",
        "Write at least a couple of pytest tests for your core logic, including one edge case.",
    ],
    "java": [
        "Separate your layers (controller, service, repository) so each class has one job.",
        "Handle exceptions with meaningful messages instead of printing stack traces.",
    ],
    "ml": [
        "Report your evaluation metric on a held-out test set, not the training data.",
        "Note in your README where the data came from and any preprocessing you applied.",
    ],
    "data-science": [
        "Label every chart's axes and add a one-line takeaway under each visual.",
        "Document how you handled missing values and outliers.",
    ],
    "flutter": [
        "Test on at least two screen sizes and check the layout doesn't overflow.",
        "Keep business logic out of widgets — move it into a separate class or state manager.",
    ],
    "devops": [
        "Make your setup reproducible: someone should be able to run it with one or two commands from your README.",
        "Never commit credentials — use environment variables or secrets.",
    ],
    "cpp": [
        "Compile with warnings on (-Wall -Wextra) and fix them.",
        "Add a few test inputs, including edge cases like empty input and very large values.",
    ],
    "cloud": [
        "Keep a billing budget alert switched on and delete resources you no longer need.",
        "Grant each service only the permissions it needs, and never use your root account for day-to-day work.",
    ],
    "cyber": [
        "Only test systems you own or have written permission to test, and say so in your post.",
        "For every issue you find, explain the risk in plain words and show the fix, not just the finding.",
    ],
    "uiux": [
        "Show the why behind your design: the user problem, what you tried, and what changed after feedback.",
        "Check colour contrast and make tap targets at least 44px so the design works for everyone.",
    ],
    "genai": [
        "Keep API keys in a .env file and never paste them into code, screenshots or videos.",
        "Show a few example inputs where your app does well and one where it struggles — it builds trust.",
    ],
    "sql": [
        "Include your schema (or an ER diagram) so reviewers can follow your queries.",
        "Format queries with one clause per line and add a short comment on what each one answers.",
    ],
}

GENERAL_TIPS = [
    "Open your LinkedIn post with the outcome in one line — what you built and why it matters. Most people only read the first two lines.",
    "Show, don't just tell: a 30–60 second screen recording or 2–3 screenshots makes your work much easier to evaluate.",
    "Mention one problem you got stuck on and how you solved it — the reasoning is often more impressive than the feature list.",
    "Push your code to a public GitHub repo with a README (what it does, how to run it, screenshots) and share the link in your post or its comments.",
    "Keep commits small with clear messages — it shows how you work, not just what you shipped.",
    "Tag the main technologies you used (e.g. #JavaScript, #Python) so your post reaches people in that field.",
]


def build_feedback(domain: str, student_id: int, week: int) -> dict:
    """Feedback for one student's submission of one week's task."""
    track = get_project_track_for_student(domain, student_id) or {}
    week_data = (track.get("weeks") or {}).get(str(week)) or {}
    offset = (int(week) - 1) * 3 % len(GENERAL_TIPS)  # rotate so each week reads differently
    return {
        "project_name": track.get("project_name") or "your project",
        "task_title": week_data.get("title") or f"Week {week} task",
        "checklist": list(week_data.get("deliverables") or []),
        "stage_tip": STAGE_TIPS.get(int(week), ""),
        "domain_tips": DOMAIN_TIPS.get(resolve_domain_key(domain), []),
        "general_tips": [GENERAL_TIPS[(offset + i) % len(GENERAL_TIPS)] for i in range(3)],
    }


def feedback_to_text(week: int, fb: dict) -> str:
    """Plain-text version stored on the submission row (and shown in the dashboard)."""
    lines = [f"Week {week} — {fb['task_title']} ({fb['project_name']})", ""]
    if fb["checklist"]:
        lines.append("Before review, make sure your post clearly shows:")
        lines += [f"- {item}" for item in fb["checklist"]]
        lines.append("")
    if fb["stage_tip"]:
        lines += [fb["stage_tip"], ""]
    tips = fb["domain_tips"] + fb["general_tips"]
    if tips:
        lines.append("Tips to make it stronger:")
        lines += [f"- {tip}" for tip in tips]
    return "\n".join(lines).strip()
