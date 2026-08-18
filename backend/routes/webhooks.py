"""
SkillMe — GitHub Webhook Handler
Receives and processes GitHub webhook events for PR tracking and auto-progress.
"""

import logging
from fastapi import APIRouter, Request, HTTPException
from services.github_service import github_service
from services.batch_service import batch_service
from db.database import db

logger = logging.getLogger("skillme.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _extract_repo_batch_id(repo_name: str) -> str | None:
    """
    Extract the domain and batch info from a repo name.
    e.g., 'web-dev-batch-1' → look up batch ID from DB.
    Returns the repo_name to query the DB.
    """
    return repo_name


@router.post("/github", summary="Handle GitHub webhook events")
async def handle_github_webhook(request: Request):
    """
    Receives GitHub webhook events and processes them:
    - pull_request.opened → Record a new submission
    - pull_request.closed (merged) → Mark issue as completed, update score
    - check_suite.completed → Update PR test status
    """
    # Verify webhook signature
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not github_service.verify_webhook_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse event
    event_type = request.headers.get("X-GitHub-Event", "")
    data = await request.json()

    logger.info(f"Received webhook: {event_type} for repo {data.get('repository', {}).get('name', 'unknown')}")

    if event_type == "pull_request":
        return await _handle_pull_request(data)
    elif event_type == "check_suite":
        return await _handle_check_suite(data)
    elif event_type == "member":
        return await _handle_member(data)
    elif event_type == "ping":
        return {"status": "pong", "message": "Webhook is active"}
    else:
        return {"status": "ignored", "event": event_type}


async def _handle_pull_request(data: dict) -> dict:
    """Handle pull_request events."""
    action = data.get("action")
    pr = data.get("pull_request", {})
    repo = data.get("repository", {})
    repo_name = repo.get("name", "")
    pr_number = pr.get("number")
    pr_url = pr.get("html_url", "")
    pr_user = pr.get("user", {}).get("login", "")
    # Branch name used to detect which issue this PR belongs to.
    # When a student uses the 'Development' button on an issue, GitHub names the
    # branch '{issue_number}-{slug}', e.g. '5-add-login-page'.
    pr_head_branch = pr.get("head", {}).get("ref", "")
    pr_body = pr.get("body") or ""  # PR description — may contain 'Fixes #N'

    # Look up the batch by repo name
    batch = await db.fetch_one(
        "SELECT * FROM batches WHERE repo_name = ?", (repo_name,)
    )
    if not batch:
        logger.warning(f"Webhook for unknown repo: {repo_name}")
        return {"status": "ignored", "reason": "repo not tracked"}

    if action == "opened" or action == "reopened":
        # Record the submission, passing the branch name for precise issue matching
        result = await batch_service.record_submission(
            batch_id=batch["id"],
            student_github_username=pr_user,
            pr_number=pr_number,
            pr_url=pr_url,
            pr_head_branch=pr_head_branch or None,
            pr_body=pr_body or None,
        )
        if result:
            logger.info(f"Recorded PR #{pr_number} by {pr_user} in {repo_name} (branch: {pr_head_branch})")
            return {"status": "submission_recorded", **result}
        else:
            return {"status": "ignored", "reason": "student not found or not enrolled"}

    elif action == "closed":
        merged = pr.get("merged", False)
        if merged:
            # Ensure submission exists before updating (lazy creation)
            submission = await db.fetch_one(
                "SELECT id FROM submissions WHERE batch_id = ? AND pr_number = ?",
                (batch["id"], pr_number)
            )
            if not submission:
                await batch_service.record_submission(
                    batch_id=batch["id"],
                    student_github_username=pr_user,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    pr_head_branch=pr_head_branch or None,
                    pr_body=pr_body or None,
                )

            # PR was merged — update progress
            await batch_service.update_submission_status(
                batch_id=batch["id"],
                pr_number=pr_number,
                status="merged",
            )
            logger.info(f"PR #{pr_number} merged in {repo_name}")
            return {"status": "pr_merged", "pr_number": pr_number}
        else:
            # PR was closed without merging
            await batch_service.update_submission_status(
                batch_id=batch["id"],
                pr_number=pr_number,
                status="closed",
            )
            return {"status": "pr_closed", "pr_number": pr_number}

    return {"status": "ignored", "action": action}


async def _handle_member(data: dict) -> dict:
    """Handle member events (e.g. collaborator accepted invite)."""
    action = data.get("action")
    if action != "added":
        return {"status": "ignored", "action": action}

    member = data.get("member", {})
    repo = data.get("repository", {})
    username = member.get("login", "")
    repo_name = repo.get("name", "")

    if not username or not repo_name:
        return {"status": "ignored", "reason": "missing member or repo"}

    # Look up the batch and student to update the enrollment
    try:
        batch = await db.fetch_one("SELECT id FROM batches WHERE repo_name = ?", (repo_name,))
        student = await db.fetch_one("SELECT id FROM students WHERE github_username = ? COLLATE NOCASE", (username,))
        
        if batch and student:
            await db.execute(
                "UPDATE enrollments SET github_invite_status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE student_id = ? AND batch_id = ?",
                (student["id"], batch["id"])
            )
            logger.info(f"GitHub invite accepted for {username} on {repo_name}")
            return {"status": "invite_accepted", "username": username}
    except Exception as e:
        logger.error(f"Error processing member webhook for {username}: {e}")
        return {"status": "error", "message": str(e)}

    return {"status": "ignored", "reason": "student or batch not found"}


async def _handle_check_suite(data: dict) -> dict:
    """Handle check_suite events (CI test results)."""
    action = data.get("action")
    if action != "completed":
        return {"status": "ignored", "action": action}

    check_suite = data.get("check_suite", {})
    repo = data.get("repository", {})
    repo_name = repo.get("name", "")
    conclusion = check_suite.get("conclusion", "")  # success, failure, neutral, etc.

    # Find associated PRs
    pull_requests = check_suite.get("pull_requests", [])
    if not pull_requests:
        head_branch = check_suite.get("head_branch")
        if head_branch and repo_name:
            try:
                open_prs = await github_service.list_pull_requests(repo_name, state="open")
                pull_requests = [pr for pr in open_prs if pr.get("head", {}).get("ref") == head_branch]
            except Exception as e:
                logger.error(f"Fallback PR lookup failed for branch {head_branch}: {e}")

    if not pull_requests:
        return {"status": "ignored", "reason": "no associated PRs"}

    # Look up batch
    batch = await db.fetch_one(
        "SELECT * FROM batches WHERE repo_name = ?", (repo_name,)
    )
    if not batch:
        return {"status": "ignored", "reason": "repo not tracked"}

    results = []
    for pr in pull_requests:
        pr_number = pr.get("number")
        if conclusion == "success":
            await batch_service.update_submission_status(
                batch_id=batch["id"],
                pr_number=pr_number,
                status="tests_passed",
            )
            # Post a success comment and auto-merge
            try:
                await github_service.add_pr_comment(
                    repo_name=repo_name,
                    pr_number=pr_number,
                    body="✅ **All tests passed!** Great work. Your PR is being automatically merged.\n\n— SkillMe Bot 🤖",
                )
                # Auto-merge the PR
                await github_service.merge_pull_request(
                    repo_name=repo_name,
                    pr_number=pr_number
                )
            except Exception as e:
                logger.error(f"Failed to auto-merge or comment on PR #{pr_number}: {e}")

            results.append({"pr_number": pr_number, "status": "tests_passed"})

        elif conclusion == "failure":
            await batch_service.update_submission_status(
                batch_id=batch["id"],
                pr_number=pr_number,
                status="tests_failed",
            )
            # Post a failure comment
            try:
                await github_service.add_pr_comment(
                    repo_name=repo_name,
                    pr_number=pr_number,
                    body="❌ **Some tests failed.** Please check the CI logs, fix the issues, and push again. Your PR will be re-tested automatically.\n\n— SkillMe Bot 🤖",
                )
            except Exception as e:
                logger.error(f"Failed to comment on PR #{pr_number}: {e}")

            results.append({"pr_number": pr_number, "status": "tests_failed"})

    return {"status": "processed", "results": results}
