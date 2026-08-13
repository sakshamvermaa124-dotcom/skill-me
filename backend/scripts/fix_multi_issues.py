import asyncio
import os
import sys
import re

# Add the parent directory to the path so we can import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.github_service import github_service
from services.batch_service import batch_service
from config import settings

async def main():
    await db.connect()
    
    # 1. Get all batches
    batches = await db.fetch_all("SELECT id, repo_name FROM batches")
    
    total_fixed = 0
    
    for batch in batches:
        batch_id = batch["id"]
        repo_name = batch["repo_name"]
        
        print(f"Processing batch {batch_id} ({repo_name})...")
        
        # 2. Get all distinct merged PR numbers for this batch
        merged_prs = await db.fetch_all(
            "SELECT DISTINCT pr_number FROM submissions WHERE batch_id = ? AND status = 'merged'",
            (batch_id,)
        )
        
        if not merged_prs:
            continue
            
        for pr_row in merged_prs:
            pr_number = pr_row["pr_number"]
            
            # Fetch PR from GitHub
            try:
                pr_data = await github_service.client.get(
                    f"/repos/{github_service.org}/{repo_name}/pulls/{pr_number}"
                )
                pr_data.raise_for_status()
                pr = pr_data.json()
            except Exception as e:
                print(f"  Error fetching PR #{pr_number}: {e}")
                continue
                
            pr_body = pr.get("body") or ""
            student_github_username = pr.get("user", {}).get("login", "")
            pr_url = pr.get("html_url", "")
            
            # Find all closing issues in the PR body
            pattern = re.compile(
                r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
                re.IGNORECASE,
            )
            closing_issue_nums = []
            for m in pattern.finditer(pr_body):
                closing_issue_nums.append(int(m.group(1)))
                
            if not closing_issue_nums:
                continue
                
            # Get the student ID
            student = await db.fetch_one(
                "SELECT id FROM students WHERE github_username = ?", 
                (student_github_username,)
            )
            if not student:
                continue
                
            # For each closing issue, check if a submission exists
            for issue_num in closing_issue_nums:
                issue = await db.fetch_one(
                    "SELECT id, status FROM issues WHERE batch_id = ? AND assigned_to = ? AND github_issue_number = ?",
                    (batch_id, student["id"], issue_num)
                )
                if not issue:
                    continue
                    
                existing_submission = await db.fetch_one(
                    "SELECT id FROM submissions WHERE batch_id = ? AND pr_number = ? AND issue_id = ?",
                    (batch_id, pr_number, issue["id"])
                )
                
                if not existing_submission:
                    print(f"  Fixing PR #{pr_number} -> Issue #{issue_num}")
                    # Insert it as open
                    await db.insert(
                        """INSERT INTO submissions (issue_id, student_id, batch_id, pr_url, pr_number, status)
                           VALUES (?, ?, ?, ?, ?, 'open')""",
                        (issue["id"], student["id"], batch_id, pr_url, pr_number),
                    )
                    total_fixed += 1
                    
            # After inserting all missing submissions for this PR, call update_submission_status
            # This will process any newly inserted 'open' submissions and mark them merged, updating progress!
            await batch_service.update_submission_status(batch_id, pr_number, "merged")
            
    print(f"\nDone! Fixed {total_fixed} missing multi-issue submissions.")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
