"""
SkillMe — Standalone Diagnostic (httpx only, no native modules)
Uses Turso HTTP API + GitHub REST API directly.
"""

import asyncio
import httpx
import json
import sys

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")


# ── Config (from .env) ──────────────────────────────────────────────────────
TURSO_URL   = "libsql://skillme-db-saksahm.aws-ap-south-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODU1MTg5NjksImlkIjoiMDE5ZmI5MzctYWQwMS03YjM3LTgyZTctZjJmOWIyMzg3NDUzIiwia2lkIjoiSDdIWkFQenRlbTMzNVMwNS1CNzNjYU5XNUUtNmVsb1BXaEtyalhpcF9TNCIsInJpZCI6IjNiNWI5MWE3LWRkMzEtNDBlMi05ZmRmLWVlNjk3MzM0MjNlNiJ9.IkHKCZPMUTZv9jygU0QWGsVrhUIGpudJ9DECxaBH5TEa7uX44LtIXhCfCGbcpxsC7V-eIHvsyC6QyMKj8Lt_Ag"
GITHUB_TOKEN = os.environ.get("SKILLME_GITHUB_TOKEN", "")
GITHUB_ORG   = "sakshamvermaa124-dotcom"
TASKS_REPO   = "SkillMe-Intern-Tasks"

# Turso HTTP endpoint
TURSO_HTTP = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"

SEP  = "─" * 62
PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

# ── Turso query helper ───────────────────────────────────────────────────────
async def db_query(client: httpx.AsyncClient, sql: str, args: list = []) -> list[dict]:
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [{"type": "text", "value": str(a)} for a in args]}},
            {"type": "close"}
        ]
    }
    r = await client.post(TURSO_HTTP, json=payload,
                          headers={"Authorization": f"Bearer {TURSO_TOKEN}"})
    r.raise_for_status()
    data = r.json()
    result = data["results"][0]
    if result["type"] == "error":
        raise RuntimeError(result["error"])
    cols = [c["name"] for c in result["response"]["result"]["cols"]]
    rows = []
    for row in result["response"]["result"]["rows"]:
        rows.append(dict(zip(cols, [cell.get("value") for cell in row])))
    return rows

# ── GitHub helper ────────────────────────────────────────────────────────────
async def gh_get(client: httpx.AsyncClient, path: str, params: dict = {}) -> tuple[int, any]:
    r = await client.get(f"https://api.github.com{path}", params=params,
                         headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                                  "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body

# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    async with httpx.AsyncClient(timeout=20) as client:

        print(f"\n{SEP}")
        print("  SkillMe Diagnostic — Data Science Batch")
        print(f"{SEP}\n")

        # ── 1. Batches ───────────────────────────────────────────────────────
        print("1. BATCHES IN DATABASE")
        try:
            batches = await db_query(client,
                "SELECT * FROM batches WHERE lower(domain) IN ('datascience','data-science','data science') ORDER BY created_at DESC")
        except Exception as e:
            batches = []
            print(f"   {FAIL} DB error: {e}")

        if not batches:
            print(f"   {FAIL} No datascience batch found!")
            print("       → Go to admin panel → Batches → Create batch with domain = 'datascience'")
            # also show ALL batches so we can see what exists
            all_b = await db_query(client, "SELECT id, domain, repo_name, status FROM batches ORDER BY created_at DESC LIMIT 10")
            print(f"\n   All batches in DB:")
            for b in all_b:
                print(f"     id={b['id']}  domain='{b['domain']}'  repo='{b['repo_name']}'  status={b['status']}")
            return

        for b in batches:
            print(f"   {PASS} id={b['id']}  domain='{b['domain']}'  repo='{b['repo_name']}'  status={b['status']}")

        batch   = batches[0]
        batch_id  = batch["id"]
        domain    = batch["domain"]
        repo_name = batch["repo_name"]
        print()

        # ── 2. Enrolled students ─────────────────────────────────────────────
        print("2. ENROLLED STUDENTS")
        try:
            enrollments = await db_query(client,
                """SELECT e.student_id, e.status, e.github_invite_status,
                          s.first_name, s.last_name, s.email, s.github_username
                   FROM enrollments e
                   JOIN students s ON e.student_id = s.id
                   WHERE e.batch_id = ? AND e.status != 'dropped'""",
                [batch_id])
        except Exception as e:
            enrollments = []
            print(f"   {FAIL} DB error: {e}")

        if not enrollments:
            print(f"   {WARN} No active enrollments in batch {batch_id}.")
        for e in enrollments:
            gh = e["github_username"] or "(no GitHub)"
            print(f"   {PASS} student_id={e['student_id']}  {e['first_name']} {e['last_name']}")
            print(f"        email={e['email']}")
            print(f"        GitHub=@{gh}  invite_status={e.get('github_invite_status','?')}")
        print()

        # ── 3. Issues in DB ──────────────────────────────────────────────────
        print("3. ISSUES ASSIGNED IN DB")
        try:
            issues = await db_query(client,
                "SELECT id, title, week_number, assigned_to, status, github_issue_number FROM issues WHERE batch_id = ? ORDER BY week_number, id",
                [batch_id])
        except Exception as e:
            issues = []
            print(f"   {FAIL} DB error: {e}")

        if not issues:
            print(f"   {WARN} No issues recorded in DB for batch {batch_id}.")
            print(f"       → Tasks have not been assigned yet, or assignment failed.")
        else:
            for iss in issues:
                print(f"   {PASS} issue_id={iss['id']}  gh_issue=#{iss['github_issue_number']}  week={iss['week_number']}  assigned_to={iss['assigned_to']}  status={iss['status']}")
                print(f"        {iss['title'][:72]}")
        print()

        # ── 4. GitHub repo ───────────────────────────────────────────────────
        print(f"4. GITHUB REPO  {GITHUB_ORG}/{repo_name}")
        status, repo_info = await gh_get(client, f"/repos/{GITHUB_ORG}/{repo_name}")
        if status == 200:
            print(f"   {PASS} {repo_info['html_url']}")
            print(f"        private={repo_info['private']}  default_branch={repo_info['default_branch']}")
        elif status == 404:
            print(f"   {FAIL} Repo '{repo_name}' NOT found on GitHub!")
        else:
            print(f"   {WARN} HTTP {status}: {repo_info}")
        print()

        # ── 5. Collaborators ─────────────────────────────────────────────────
        print("5. GITHUB COLLABORATORS")
        status, collabs_data = await gh_get(client,
            f"/repos/{GITHUB_ORG}/{repo_name}/collaborators", {"per_page": 50})
        if status == 200:
            collab_logins = [c["login"] for c in collabs_data]
            print(f"   Collaborators: {collab_logins or 'none'}")
            for e in enrollments:
                gh = e.get("github_username")
                if gh:
                    if gh in collab_logins:
                        print(f"   {PASS} @{gh} IS a collaborator")
                    else:
                        print(f"   {FAIL} @{gh} NOT a collaborator — check pending invites on GitHub")
        else:
            print(f"   {WARN} HTTP {status} — could not list collaborators")
        print()

        # ── 6. Tasks repo: check folder exists ──────────────────────────────
        # Resolve slug  (same logic as task_service.DOMAIN_SLUG_MAP)
        SLUG_MAP = {
            "datascience": "datascience", "data-science": "datascience",
            "Data Science": "datascience",
            "web-dev": "web-dev", "Web Development": "web-dev",
            "python": "python", "Python": "python",
            "ml": "ml", "Machine Learning": "ml",
            "devops": "devops", "flutter": "flutter",
            "react": "react", "node": "node", "java": "java",
            "cpp": "cpp", "cyber": "cyber", "cloud": "cloud",
            "dsa": "dsa", "blockchain": "blockchain",
            "android": "android", "sql": "sql", "genai": "genai",
            "uiux": "uiux",
        }
        slug = SLUG_MAP.get(domain, domain.lower().replace(" ", "-").replace("/", "-"))
        folder_path = f"{slug}/week-1"

        print(f"6. TASKS REPO  {TASKS_REPO}/{folder_path}")
        print(f"   (domain='{domain}'  →  slug='{slug}')")

        status, folder = await gh_get(client,
            f"/repos/{GITHUB_ORG}/{TASKS_REPO}/contents/{folder_path}")
        if status == 200:
            md_files = [f for f in folder if isinstance(f, dict) and f["name"].endswith(".md")]
            print(f"   {PASS} Folder exists with {len(md_files)} markdown file(s):")
            for f in md_files:
                print(f"        • {f['name']}  ({f['size']} bytes)")
        elif status == 404:
            print(f"   {FAIL} Folder '{folder_path}' NOT found in {TASKS_REPO}!")
            print(f"       → Check the repo: https://github.com/{GITHUB_ORG}/{TASKS_REPO}")
            # List what folders DO exist
            status2, root = await gh_get(client, f"/repos/{GITHUB_ORG}/{TASKS_REPO}/contents/{slug}")
            if status2 == 200:
                print(f"       Available weeks in '{slug}/': {[f['name'] for f in root if isinstance(f, dict)]}")
            else:
                status3, root2 = await gh_get(client, f"/repos/{GITHUB_ORG}/{TASKS_REPO}/contents")
                if status3 == 200:
                    print(f"       Top-level folders: {[f['name'] for f in root2 if isinstance(f, dict)]}")
        else:
            print(f"   {WARN} HTTP {status}: {folder}")
        print()

        # ── 7. GitHub issues on batch repo ───────────────────────────────────
        print(f"7. GITHUB ISSUES ON  {repo_name}")
        status, gh_issues = await gh_get(client,
            f"/repos/{GITHUB_ORG}/{repo_name}/issues", {"state": "open", "per_page": 20})
        if status == 200 and isinstance(gh_issues, list):
            if gh_issues:
                print(f"   {PASS} {len(gh_issues)} open issue(s):")
                for gi in gh_issues[:10]:
                    assignees = [a["login"] for a in gi.get("assignees", [])]
                    print(f"        #{gi['number']} — {gi['title'][:60]}")
                    print(f"             assignees={assignees or 'none'}")
            else:
                print(f"   {WARN} No open issues on GitHub for '{repo_name}'.")
                print(f"       → Tasks were not pushed to GitHub yet.")
        elif status == 404:
            print(f"   {FAIL} Repo not found on GitHub")
        else:
            print(f"   {WARN} HTTP {status}")
        print()

        print(f"{SEP}")
        print("  Diagnostic complete.")
        print(f"{SEP}\n")

if __name__ == "__main__":
    asyncio.run(main())
