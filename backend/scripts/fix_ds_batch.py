"""
SkillMe — Fix Script for data-science-batch-1
1. Creates the GitHub repo from ml-template (or web-dev-template as fallback)
2. Re-invites student as collaborator
3. Creates the Week 1 issues on GitHub and updates DB records
Run from backend/ folder.
"""

import asyncio
import httpx
import sys
import base64
import os

sys.stdout.reconfigure(encoding="utf-8")

GITHUB_TOKEN  = os.environ.get("SKILLME_GITHUB_TOKEN", "")
GITHUB_ORG    = "sakshamvermaa124-dotcom"
TASKS_REPO    = "SkillMe-Intern-Tasks"
REPO_NAME     = "data-science-batch-1"
DOMAIN_SLUG   = "datascience"   # repo folder in SkillMe-Intern-Tasks
STUDENT_GH    = "debanjanhati2-boop"
BATCH_ID      = 3
STUDENT_ID    = 10
WEEK          = 1

TURSO_HTTP    = "https://skillme-db-saksahm.aws-ap-south-1.turso.io/v2/pipeline"
TURSO_TOKEN   = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODU1MTg5NjksImlkIjoiMDE5ZmI5MzctYWQwMS03YjM3LTgyZTctZjJmOWIyMzg3NDUzIiwia2lkIjoiSDdIWkFQenRlbTMzNVMwNS1CNzNjYU5XNUUtNmVsb1BXaEtyalhpcF9TNCIsInJpZCI6IjNiNWI5MWE3LWRkMzEtNDBlMi05ZmRmLWVlNjk3MzM0MjNlNiJ9.IkHKCZPMUTZv9jygU0QWGsVrhUIGpudJ9DECxaBH5TEa7uX44LtIXhCfCGbcpxsC7V-eIHvsyC6QyMKj8Lt_Ag"

GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
PASS = "✅"; FAIL = "❌"; WARN = "⚠️ "; INFO = "ℹ️ "

async def db_exec(client, sql, args=[]):
    payload = {"requests": [
        {"type": "execute", "stmt": {"sql": sql, "args": [{"type": "text", "value": str(a)} for a in args]}},
        {"type": "close"}
    ]}
    r = await client.post(TURSO_HTTP, json=payload, headers={"Authorization": f"Bearer {TURSO_TOKEN}"})
    r.raise_for_status()
    data = r.json()
    res = data["results"][0]
    if res["type"] == "error":
        raise RuntimeError(res["error"])
    return res

async def gh(client, method, path, **kwargs):
    r = await client.request(method, f"https://api.github.com{path}", headers=GH_HEADERS, **kwargs)
    try: body = r.json()
    except: body = r.text
    return r.status_code, body

async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        print("\n── Step 1: Check/Create GitHub Repo ──────────────────────────")

        # Check if repo exists
        status, repo = await gh(client, "GET", f"/repos/{GITHUB_ORG}/{REPO_NAME}")
        if status == 200:
            print(f"{PASS} Repo already exists: {repo['html_url']}")
        else:
            print(f"{INFO} Repo not found. Creating from ml-template...")
            # Try ml-template first, then web-dev-template
            for template in ["ml-template", "web-dev-template"]:
                status2, result = await gh(client, "POST",
                    f"/repos/{GITHUB_ORG}/{template}/generate",
                    json={
                        "owner": GITHUB_ORG,
                        "name": REPO_NAME,
                        "description": "SkillMe Data Science Internship — Batch 1",
                        "private": False,
                        "include_all_branches": False,
                    })
                if status2 in (201, 202):
                    print(f"{PASS} Repo created from {template}: {result.get('html_url','')}")
                    break
                else:
                    print(f"{WARN} Template '{template}' failed (HTTP {status2}): {result.get('message','')}")
            else:
                print(f"{FAIL} Could not create repo from any template. Check if templates exist on GitHub.")
                print("     Create 'data-science-batch-1' manually on GitHub, then re-run this script.")
                return

        print()
        print("── Step 2: Add Student as Collaborator ───────────────────────")
        status3, invite = await gh(client, "PUT",
            f"/repos/{GITHUB_ORG}/{REPO_NAME}/collaborators/{STUDENT_GH}",
            json={"permission": "push"})
        if status3 in (201, 204):
            print(f"{PASS} @{STUDENT_GH} invited/added as collaborator (HTTP {status3})")
            # Update DB
            await db_exec(client,
                "UPDATE enrollments SET github_invite_status='pending' WHERE student_id=? AND batch_id=?",
                [STUDENT_ID, BATCH_ID])
            print(f"     DB enrollment updated → invite_status='pending'")
        else:
            print(f"{FAIL} Could not add collaborator (HTTP {status3}): {invite}")

        print()
        print("── Step 3: Fetch Tasks from SkillMe-Intern-Tasks ─────────────")
        status4, folder = await gh(client,
            "GET", f"/repos/{GITHUB_ORG}/{TASKS_REPO}/contents/{DOMAIN_SLUG}/week-{WEEK}")
        if status4 != 200:
            print(f"{FAIL} Could not read tasks folder (HTTP {status4})")
            return

        md_files = [f for f in folder if isinstance(f, dict) and f["name"].endswith(".md")]
        print(f"{PASS} Found {len(md_files)} task file(s) in {DOMAIN_SLUG}/week-{WEEK}")
        tasks = []
        for f in md_files:
            s5, fdata = await gh(client, "GET", f["url"].replace("https://api.github.com",""))
            if s5 == 200 and "content" in fdata:
                content = base64.b64decode(fdata["content"]).decode("utf-8")
                # Simple parse: use filename as title, full content as body
                import re, yaml
                match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
                if match:
                    try:
                        fm = yaml.safe_load(match.group(1)) or {}
                    except:
                        fm = {}
                    title = fm.get("title", f["name"].replace(".md","").replace("-"," ").title())
                    body = match.group(2).strip()
                    difficulty = fm.get("difficulty","medium")
                else:
                    title = f["name"].replace(".md","").replace("-"," ").title()
                    body = content.strip()
                    difficulty = "medium"
                tasks.append({"title": title, "body": body, "difficulty": difficulty, "filename": f["name"]})
                print(f"     • {title[:60]}")

        print()
        print("── Step 4: Create GitHub Issues + Update DB ──────────────────")
        WEEK_LABEL = f"week-{WEEK}"
        issue_ids_to_update = []

        # Fetch existing DB issue ids for this batch/week/student
        res = await db_exec(client,
            "SELECT id FROM issues WHERE batch_id=? AND week_number=? AND assigned_to=? ORDER BY id",
            [BATCH_ID, WEEK, STUDENT_ID])
        existing_ids = []
        if res["type"] != "error":
            cols = [c["name"] for c in res["response"]["result"]["cols"]]
            for row in res["response"]["result"]["rows"]:
                d = dict(zip(cols, [cell.get("value") for cell in row]))
                existing_ids.append(d["id"])
        print(f"{INFO} Existing DB issue ids for this student/week: {existing_ids}")

        for idx, task in enumerate(tasks):
            title_full = f"[Week {WEEK}] {task['title']}"
            s6, issue = await gh(client, "POST",
                f"/repos/{GITHUB_ORG}/{REPO_NAME}/issues",
                json={
                    "title": title_full,
                    "body": task["body"],
                    "assignees": [STUDENT_GH],
                    "labels": [WEEK_LABEL, task["difficulty"]],
                })
            if s6 == 201:
                gh_num = issue["number"]
                print(f"{PASS} Created GitHub issue #{gh_num}: {title_full[:55]}")
                # Update DB record if we have one
                if idx < len(existing_ids):
                    db_id = existing_ids[idx]
                    await db_exec(client,
                        "UPDATE issues SET github_issue_number=?, status='assigned' WHERE id=?",
                        [gh_num, db_id])
                    print(f"     DB issue id={db_id} updated with github_issue_number={gh_num}")
            else:
                # Try without assignee (invite still pending)
                s7, issue2 = await gh(client, "POST",
                    f"/repos/{GITHUB_ORG}/{REPO_NAME}/issues",
                    json={
                        "title": title_full,
                        "body": task["body"],
                        "labels": [WEEK_LABEL, task["difficulty"]],
                    })
                if s7 == 201:
                    gh_num = issue2["number"]
                    print(f"{WARN} Created issue #{gh_num} WITHOUT assignee (invite pending): {title_full[:45]}")
                    if idx < len(existing_ids):
                        db_id = existing_ids[idx]
                        await db_exec(client,
                            "UPDATE issues SET github_issue_number=?, status='assigned' WHERE id=?",
                            [gh_num, db_id])
                        print(f"     DB issue id={db_id} updated → github_issue_number={gh_num}")
                else:
                    print(f"{FAIL} Could not create issue (HTTP {s7}): {issue2.get('message','')}")

        print()
        print("── Done! ─────────────────────────────────────────────────────")
        print(f"  Repo URL : https://github.com/{GITHUB_ORG}/{REPO_NAME}")
        print(f"  Student  : @{STUDENT_GH} — ask them to accept the GitHub invite in their email")
        print(f"  Issues   : https://github.com/{GITHUB_ORG}/{REPO_NAME}/issues")
        print()

if __name__ == "__main__":
    asyncio.run(main())
