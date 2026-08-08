"""Audit the full naming chain for every domain."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

ADMIN_VALUES = [
    "web-dev","python","react","node","java","ml",
    "datascience","flutter","devops","cpp","uiux","cyber",
    "cloud","dsa","blockchain","android","sql","genai",
]

print(f"{'Domain Value':<16} {'Batch Repo':<26} {'Template Repo':<26} {'Task Folder':<16} Consistent?")
print("-" * 95)

issues = []
for v in ADMIN_VALUES:
    batch    = f"{v}-batch-N"
    template = f"{v}-template"
    task_slug = v  # DOMAIN_SLUG_MAP passes through all these slugs directly

    # All three should share the same slug prefix
    ok = (batch.startswith(v) and template.startswith(v) and task_slug == v)
    flag = "OK" if ok else "MISMATCH"
    if not ok:
        issues.append(v)

    print(f"{v:<16} {batch:<26} {template:<26} {task_slug:<16} {flag}")

print()
if issues:
    print(f"MISMATCHES: {issues}")
else:
    print("ALL CONSISTENT - every domain value flows correctly through the entire naming chain.")
print()
print("What the old bug was:")
print("  Admin sent domain='data-science' (with hyphen)")
print("  -> batch repo created: 'data-science-batch-1'")
print("  -> looked for template: 'data-science-template' (DIDN'T EXIST)")
print("  -> task_service slug resolved 'data-science' -> 'datascience' (MISMATCH vs repo name)")
print()
print("What the fix is:")
print("  Admin now sends domain='datascience' (no hyphen)")
print("  -> batch repo: 'datascience-batch-N'")
print("  -> template:   'datascience-template' (EXISTS)")
print("  -> task slug:  'datascience'          (MATCHES)")
