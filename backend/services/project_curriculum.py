"""
SkillMe — Multi-Domain 4-Week Incremental Project Curriculum Loader
Loads and serves 4-week project tracks from backend/services/curriculum.json.
"""

import json
from pathlib import Path

from services.task_service import task_service

DATA_FILE = Path(__file__).resolve().parent / "curriculum.json"

try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        PROJECT_CURRICULUM = json.load(f)
except Exception:
    PROJECT_CURRICULUM = {}

# task_service slugs that have no curriculum of their own → closest curriculum key
_SLUG_TO_CURRICULUM = {
    "datascience": "data-science",
    "android": "flutter",
    "dsa": "cpp",
    "blockchain": "web-dev",
}


def resolve_domain_key(domain: str) -> str:
    d = (domain or "").lower().strip()
    if d in PROJECT_CURRICULUM:
        return d
    slug = task_service.normalize_domain_slug(domain)
    slug = _SLUG_TO_CURRICULUM.get(slug, slug)
    return slug if slug in PROJECT_CURRICULUM else "web-dev"

def get_project_track_for_student(domain: str, student_id: int) -> dict:
    key = resolve_domain_key(domain)
    tracks = PROJECT_CURRICULUM.get(key, PROJECT_CURRICULUM.get("web-dev", []))
    if not tracks:
        return {}
    track_idx = int(student_id or 1) % len(tracks)
    return tracks[track_idx]
