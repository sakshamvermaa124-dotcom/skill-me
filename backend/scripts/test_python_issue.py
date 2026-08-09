import asyncio
from config import settings
from services.github_service import github_service

async def main():
    try:
        gh_issue = await github_service.create_issue(
            repo_name="python-batch-1",
            title="Test Issue",
            body="Test body",
            assignee=None,
            labels=["test"],
        )
        print("Success:", gh_issue)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
