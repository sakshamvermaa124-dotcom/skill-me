"""
SkillMe — Clear all student data via Turso HTTP API.
No libsql_experimental needed — uses plain HTTP requests.
"""
import json
import requests

TURSO_URL = "https://skillme-db-saksahm.aws-ap-south-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODU1MTg5NjksImlkIjoiMDE5ZmI5MzctYWQwMS03YjM3LTgyZTctZjJmOWIyMzg3NDUzIiwia2lkIjoiSDdIWkFQenRlbTMzNVMwNS1CNzNjYU5XNUUtNmVsb1BXaEtyalhpcF9TNCIsInJpZCI6IjNiNWI5MWE3LWRkMzEtNDBlMi05ZmRmLWVlNjk3MzM0MjNlNiJ9.IkHKCZPMUTZv9jygU0QWGsVrhUIGpudJ9DECxaBH5TEa7uX44LtIXhCfCGbcpxsC7V-eIHvsyC6QyMKj8Lt_Ag"

HEADERS = {
    "Authorization": f"Bearer {TURSO_TOKEN}",
    "Content-Type": "application/json",
}

PIPELINE_URL = f"{TURSO_URL}/v2/pipeline"


def execute(statements: list[str]):
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql}}
            for sql in statements
        ] + [{"type": "close"}]
    }
    resp = requests.post(PIPELINE_URL, headers=HEADERS, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def count(table: str) -> int:
    result = execute([f"SELECT COUNT(*) as c FROM {table}"])
    try:
        return result["results"][0]["response"]["result"]["rows"][0][0]["value"]
    except Exception:
        return "?"


TABLES = ["students", "enrollments", "issues", "submissions", "progress", "payments", "certificates"]

print("=== COUNTS BEFORE ===")
for t in TABLES:
    print(f"  {t:<15} {count(t)}")

print("\nClearing all student data (batches kept)...")

# Delete in dependency order (children first)
delete_statements = [
    "DELETE FROM payments",
    "DELETE FROM certificates",
    "DELETE FROM submissions",
    "DELETE FROM progress",
    "DELETE FROM issues",
    "DELETE FROM enrollments",
    "DELETE FROM students",
]

result = execute(delete_statements)

# Check for errors
for i, r in enumerate(result.get("results", [])):
    if r.get("type") == "error":
        print(f"  ERROR on statement {i}: {r['error']}")

print("\n=== COUNTS AFTER ===")
for t in TABLES:
    print(f"  {t:<15} {count(t)}")

print("\nDone! All student data cleared successfully.")
