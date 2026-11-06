"""
SkillMe — Track-specific first-task content for onboarding (student dashboard + emails).

Read-only: pulls the student's real project and weekly milestone from the curriculum, and
adds a short "get set up" list and "what to submit" line per track family. Nothing here
changes which task a student is assigned.
"""
from __future__ import annotations

from services.project_curriculum import get_project_track_for_student, resolve_domain_key

# curriculum key -> (family, setup checklist, what "proof" to put in the LinkedIn post)
_FAMILIES = {
    "web": (["VS Code (or any editor)", "Git and a free GitHub account", "A modern browser with dev tools"],
            "your GitHub repo link and a short screen recording of the page working"),
    "python": (["Python 3.10+ installed", "VS Code (or PyCharm)", "Git and a free GitHub account"],
               "your GitHub repo link and a screenshot or recording of the program running"),
    "data": (["Google Colab or Jupyter", "pandas and matplotlib (preinstalled on Colab)", "A free GitHub account to host the notebook"],
             "your notebook link (GitHub or Colab) and one chart or insight screenshot"),
    "ml": (["Google Colab or Jupyter", "scikit-learn (preinstalled on Colab)", "A free GitHub account to host the notebook"],
           "your notebook link (GitHub or Colab) and the metric or plot your model produced"),
    "design": (["A free Figma account", "A reference to 2 to 3 apps you like"],
               "your Figma file link (set to view) and a screenshot of the main screen"),
    "ops": (["Docker Desktop or a free cloud account", "Git and a free GitHub account", "A terminal you are comfortable in"],
            "your GitHub repo link and a screenshot of the running setup"),
    "product": (["A doc tool (Notion or Google Docs)", "30 minutes of focused research time"],
                "a link to your doc and the 2 or 3 key findings in the post"),
    "general": (["The tools named in your Week 1 brief", "A free GitHub account"],
                "a link to your work (GitHub, Colab or Figma) and a short summary of what you built"),
}
_KEY_TO_FAMILY = {
    "web-dev": "web", "react": "web", "node": "web", "sql": "web", "java": "web", "flutter": "web",
    "cpp": "python", "sde": "python", "python": "python", "qa": "python",
    "data-science": "data", "ml": "ml", "genai": "ml", "ai-engineer": "ml",
    "uiux": "design", "devops": "ops", "cloud": "ops", "cyber": "ops",
    "ai-pm": "product", "fde": "general",
}


def family_for(domain: str) -> str:
    return _KEY_TO_FAMILY.get(resolve_domain_key(domain or ""), "general")


def _hours_label(est: str | None) -> str:
    est = (est or "2-3").replace("-", "–")
    return f"About {est} hours"


def week_content(domain: str, student_id: int, week: int) -> dict:
    """Project + milestone details for one week of this student's assigned track."""
    track = get_project_track_for_student(domain, student_id) or {}
    wk = (track.get("weeks") or {}).get(str(week)) or {}
    return {
        "project_name": track.get("project_name") or "",
        "tagline": track.get("tagline") or "",
        "week": week,
        "title": wk.get("title") or f"Week {week} milestone",
        "difficulty": wk.get("difficulty") or "Beginner",
        "est_hours": wk.get("est_hours") or "2-3",
        "time_label": _hours_label(wk.get("est_hours")),
        "deliverables": [d.replace("`", "") for d in (wk.get("deliverables") or [])][:5],
    }


def first_task_content(domain: str, student_id: int) -> dict:
    """Everything the onboarding card and first-task emails need for Week 1."""
    base = week_content(domain, student_id, 1)
    setup, proof = _FAMILIES[family_for(domain)]
    base.update({
        "setup": setup,
        "submit_what": proof,
        "submit_steps": [
            "Build the Week 1 deliverables listed above.",
            f"Post about it on LinkedIn with {proof}.",
            "Copy the post's URL and paste it into the Tasks tab, then press Submit.",
        ],
        "review_note": "An admin reviews each submission. If a change is needed you can fix it and resubmit.",
    })
    return base
