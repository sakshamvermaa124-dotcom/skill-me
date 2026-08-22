import asyncio, sys, base64
sys.path.append('backend')
from services.github_service import github_service
from services.task_service import TaskService
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    ts = TaskService()
    path = "python/week-1"
    TASKS_REPO = "SkillMe-Intern-Tasks"
    print(f"Fetching from: /repos/{github_service.org}/{TASKS_REPO}/contents/{path}")
    res = await github_service.client.get(f"/repos/{github_service.org}/{TASKS_REPO}/contents/{path}")
    if res.status_code == 200:
        contents = res.json()
        print(f"Files found on API: {len(contents)}")
        for f in contents:
            if isinstance(f, dict) and f.get("name", "").endswith(".md"):
                print(f.get("name"))
    else:
        print(f"Failed: {res.status_code} {res.text}")

asyncio.run(main())
