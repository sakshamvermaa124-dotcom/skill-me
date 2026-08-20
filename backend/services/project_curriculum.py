"""
SkillMe — Multi-Domain 4-Week Incremental Project Curriculum Loader
Loads and serves 4-week project tracks from backend/services/curriculum.json.
"""

import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "curriculum.json"

try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        PROJECT_CURRICULUM = json.load(f)
except Exception:
    PROJECT_CURRICULUM = {}

def resolve_domain_key(domain: str) -> str:
    d = (domain or "").lower().strip().replace(" ", "-")
    domain_map = {
        "web": "web-dev", "front": "web-dev", "full": "web-dev", "html": "web-dev",
        "react": "react", "next": "react",
        "node": "node", "express": "node",
        "data": "data-science", "analytics": "data-science",
        "ml": "ml", "ai": "ml", "machine": "ml",
        "python": "python", "django": "python", "flask": "python",
        "java": "java", "spring": "java",
        "flutter": "flutter", "dart": "flutter", "mobile": "flutter", "android": "flutter",
        "devops": "devops", "docker": "devops", "ci": "devops", "cloud": "devops",
        "cpp": "cpp", "c++": "cpp", "algo": "cpp", "dsa": "cpp"
    }
    for kw, key in domain_map.items():
        if kw in d:
            return key
    return "web-dev"

def get_project_track_for_student(domain: str, student_id: int) -> dict:
    key = resolve_domain_key(domain)
    tracks = PROJECT_CURRICULUM.get(key, PROJECT_CURRICULUM.get("web-dev", []))
    if not tracks:
        return {}
    track_idx = int(student_id or 1) % len(tracks)
    return tracks[track_idx]
