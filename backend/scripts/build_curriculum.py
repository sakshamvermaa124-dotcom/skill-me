"""
SkillMe — Curriculum Builder

The 4-week project tracks are authored as one structured file per domain in
backend/services/curriculum/<domain>.json. This script validates them and renders
backend/services/curriculum.json, which is what the API serves.

    python backend/scripts/build_curriculum.py            # validate all + write curriculum.json
    python backend/scripts/build_curriculum.py --check    # validate only
    python backend/scripts/build_curriculum.py --check backend/services/curriculum/sql.json

Every domain must have exactly TRACKS_PER_DOMAIN tracks: students are assigned a track by
`student_id % len(tracks)`, so changing the count would move enrolled students to a
different project mid-internship.
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from services.showcase import showcase_for  # noqa: E402

SERVICES_DIR = BACKEND_DIR / "services"
SOURCE_DIR = SERVICES_DIR / "curriculum"
OUTPUT_FILE = SERVICES_DIR / "curriculum.json"

TRACKS_PER_DOMAIN = 3
# New domains launch with a single project track; existing domains keep 3.
TRACK_COUNT_OVERRIDES = {
    "ai-engineer": 1,
    "fde": 1,
    "sde": 1,
    "ai-pm": 1,
    "qa": 1,
}
WEEK_DIFFICULTY = {"1": "Beginner", "2": "Beginner+", "3": "Intermediate", "4": "Intermediate+"}

# field -> (type, min items, max items); lists only
LIST_FIELDS = {
    "learn": (3, 5),
    "steps": (4, 8),
    "deliverables": (3, 5),
    "done_when": (3, 6),
    "hints": (2, 5),
    "post_highlights": (3, 3),
}
STRING_FIELDS = ["title", "difficulty", "est_hours", "goal", "stretch"]


def validate(data: dict, source: str) -> list[str]:
    errors = []

    def err(msg):
        errors.append(f"{source}: {msg}")

    if not isinstance(data.get("domain"), str) or not data["domain"]:
        err("missing 'domain'")
    expected_tracks = TRACK_COUNT_OVERRIDES.get(data.get("domain"), TRACKS_PER_DOMAIN)
    tracks = data.get("tracks")
    if not isinstance(tracks, list) or len(tracks) != expected_tracks:
        err(f"'tracks' must be a list of exactly {expected_tracks}")
        return errors

    names = set()
    for ti, track in enumerate(tracks):
        where = f"track[{ti}]"
        for key in ("project_name", "tagline"):
            if not isinstance(track.get(key), str) or not track[key].strip():
                err(f"{where}: missing '{key}'")
        if track.get("project_name") in names:
            err(f"{where}: duplicate project_name")
        names.add(track.get("project_name"))

        weeks = track.get("weeks")
        if not isinstance(weeks, dict) or sorted(weeks) != ["1", "2", "3", "4"]:
            err(f"{where}: 'weeks' must have keys '1'..'4'")
            continue
        for wk, week in weeks.items():
            wwhere = f"{where}.week[{wk}]"
            for key in STRING_FIELDS:
                if not isinstance(week.get(key), str) or not week[key].strip():
                    err(f"{wwhere}: missing string '{key}'")
            if week.get("difficulty") != WEEK_DIFFICULTY[wk]:
                err(f"{wwhere}: difficulty must be '{WEEK_DIFFICULTY[wk]}'")
            if str(week.get("title", "")).lower().startswith("week"):
                err(f"{wwhere}: title should not start with 'Week N' (the UI adds it)")
            for key, (lo, hi) in LIST_FIELDS.items():
                val = week.get(key)
                if not isinstance(val, list) or not all(isinstance(v, str) and v.strip() for v in val):
                    err(f"{wwhere}: '{key}' must be a list of non-empty strings")
                elif not lo <= len(val) <= hi:
                    err(f"{wwhere}: '{key}' needs {lo}-{hi} items, has {len(val)}")
    return errors


def render_description(domain: str, week_no: str, week: dict) -> str:
    """Markdown shown on the dashboard (rendered with marked.js)."""
    showcase = showcase_for(domain)
    lines = [
        f"### 🎯 This Week's Goal",
        week["goal"],
        "",
        f"**Level:** {week['difficulty']} · **Estimated time:** {week['est_hours']} hours",
        "",
        "### 📚 What You'll Learn",
        *[f"- {item}" for item in week["learn"]],
        "",
        "### 🛠️ Step-by-Step",
        *[f"{i}. {step}" for i, step in enumerate(week["steps"], 1)],
        "",
        "### ✅ Done When",
        *[f"- [ ] {item}" for item in week["done_when"]],
        "",
        "### 💡 Hints & Resources",
        *[f"- {item}" for item in week["hints"]],
        "",
        "### 🚀 Stretch Goal (optional)",
        week["stretch"],
        "",
        "### 📤 Submission",
        showcase["submission"],
    ]
    if week_no != "1":
        lines.insert(1, f"This week builds on your Week {int(week_no) - 1} work — {showcase['continue']}.\n")
    return "\n".join(lines)


def render_domain(data: dict) -> list[dict]:
    tracks = []
    for track in data["tracks"]:
        weeks = {}
        for wk in ("1", "2", "3", "4"):
            week = track["weeks"][wk]
            weeks[wk] = {
                "title": week["title"],
                "difficulty": week["difficulty"],
                "est_hours": week["est_hours"],
                "deliverables": week["deliverables"],
                "description": render_description(data["domain"], wk, week),
                "post_highlights": week["post_highlights"],
            }
        tracks.append({"project_name": track["project_name"], "tagline": track["tagline"], "weeks": weeks})
    return tracks


def load(path: Path) -> tuple[dict | None, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except Exception as e:
        return None, [f"{path.name}: invalid JSON — {e}"]


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")] or sorted(SOURCE_DIR.glob("*.json"))
    if not paths:
        print(f"No source files found in {SOURCE_DIR}")
        return 1

    errors, curriculum = [], {}
    for path in paths:
        data, load_errors = load(path)
        errors += load_errors
        if data is None:
            continue
        errors += validate(data, path.name)
        if data.get("domain") and data["domain"] != path.stem:
            errors.append(f"{path.name}: 'domain' ({data['domain']}) must match the file name")
        if not errors:
            curriculum[data["domain"]] = render_domain(data)

    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} problem(s) found.")
        return 1
    if check_only:
        print(f"OK — {len(paths)} file(s) valid.")
        return 0

    OUTPUT_FILE.write_text(json.dumps(curriculum, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE} — {len(curriculum)} domains: {', '.join(curriculum)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
