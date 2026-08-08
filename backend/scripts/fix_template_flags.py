"""Fix: Mark 6 newly created template repos as GitHub template repositories."""
import httpx, asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")

import os
TOKEN = os.environ.get("SKILLME_GITHUB_TOKEN", "")
ORG   = "sakshamvermaa124-dotcom"
H     = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

NEEDS_TEMPLATE_FLAG = [
    "uiux-template", "dsa-template", "blockchain-template",
    "android-template", "sql-template", "genai-template",
]

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        for repo in NEEDS_TEMPLATE_FLAG:
            r = await c.patch(
                f"https://api.github.com/repos/{ORG}/{repo}",
                headers=H,
                json={"is_template": True},
            )
            if r.status_code == 200:
                print(f"  OK  {repo} -> marked as template repo")
            else:
                msg = r.json().get("message", "unknown error")
                print(f"  ERR {repo} -> HTTP {r.status_code}: {msg}")

asyncio.run(main())
