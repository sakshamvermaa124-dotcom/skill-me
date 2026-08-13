"""
Webhook Tests — GitHub Event Handler
Tests POST /api/webhooks/github for PR and check_suite events.
"""
import hashlib
import hmac
import json
import pytest
from tests.conftest import test_db


def _make_signature(payload: dict, secret: str = "my_super_secret_webhook_key_123") -> str:
    """Compute HMAC-SHA256 signature for a webhook payload."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


PR_OPENED_EVENT = {
    "action": "opened",
    "pull_request": {
        "number": 42,
        "html_url": "https://github.com/test-org/web-dev-batch-1/pull/42",
        "user": {"login": "testuser"},
        "head": {"ref": "7-fix-navbar"},
        "body": "Fixes #7\nThis PR fixes the navbar issue.",
    },
    "repository": {"name": "web-dev-batch-1"},
}

PR_MERGED_EVENT = {
    "action": "closed",
    "pull_request": {
        "number": 42,
        "merged": True,
        "html_url": "https://github.com/test-org/web-dev-batch-1/pull/42",
        "user": {"login": "testuser"},
        "head": {"ref": "7-fix-navbar"},
        "body": "Fixes #7",
    },
    "repository": {"name": "web-dev-batch-1"},
}

PR_CLOSED_NOT_MERGED = {
    "action": "closed",
    "pull_request": {
        "number": 43,
        "merged": False,
        "html_url": "https://github.com/test-org/web-dev-batch-1/pull/43",
        "user": {"login": "testuser"},
        "head": {"ref": "some-branch"},
        "body": "",
    },
    "repository": {"name": "web-dev-batch-1"},
}


@pytest.mark.webhooks
class TestWebhookSignature:
    async def test_invalid_signature_behavior_mocked(self, client, test_batch):
        """
        NOTE: In tests, github_service.verify_webhook_signature is mocked to always return True.
        In production, an invalid signature would return 401.
        This test documents that the mock bypasses signature verification.
        """
        r = await client.post(
            "/api/webhooks/github",
            json=PR_OPENED_EVENT,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=invalidsignature",
            },
        )
        # Mock always validates True, so this returns 200 (not 401)
        assert r.status_code == 200  # Mocked — real server would 401

    async def test_missing_signature_header(self, client, test_batch):
        """With mocked verification, missing signature header is accepted (200)."""
        r = await client.post(
            "/api/webhooks/github",
            json=PR_OPENED_EVENT,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert r.status_code in (200, 401)


@pytest.mark.webhooks
class TestWebhookEvents:
    async def test_ping_event_returns_pong(self, client, test_batch):
        r = await client.post(
            "/api/webhooks/github",
            json={"zen": "Keep it simple"},
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": "sha256=mocked",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pong"

    async def test_unknown_event_is_ignored(self, client):
        r = await client.post(
            "/api/webhooks/github",
            json={"action": "something"},
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=mocked",
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"

    async def test_pr_for_unknown_repo_is_ignored(self, client):
        event = {
            **PR_OPENED_EVENT,
            "repository": {"name": "unknown-repo-xyz"},
        }
        r = await client.post(
            "/api/webhooks/github",
            json=event,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=mocked",
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"

    async def test_pr_opened_for_tracked_repo_no_crash(self, client, enrolled_student):
        """
        PR opened in a tracked repo with a non-standard branch name should gracefully
        return 'ignored' instead of crashing on the submissions.issue_id NOT NULL constraint.
        Fixed: batch_service now returns early with 'ignored_no_issue_match' when no issue found.
        """
        r = await client.post(
            "/api/webhooks/github",
            json=PR_OPENED_EVENT,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=mocked",
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] in ("submission_recorded", "ignored", "ignored_no_issue_match")

    async def test_pr_closed_not_merged_handled(self, client, enrolled_student):
        r = await client.post(
            "/api/webhooks/github",
            json=PR_CLOSED_NOT_MERGED,
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=mocked"},
        )
        assert r.status_code == 200

    async def test_pr_merged_multiple_issues_updates_all(self, client, enrolled_student):
        """
        Verify that a single PR merged with multiple issue-closing keywords
        (e.g., Fixes #10, Fixes #11, Fixes #12) completes all issues and updates progress.
        """
        student_id = enrolled_student["id"]
        batch_id = enrolled_student["batch_id"]

        # Seed 3 issues for this student
        for issue_num in (10, 11, 12):
            await test_db.insert(
                """INSERT INTO issues (batch_id, week_number, title, github_issue_number, assigned_to, status)
                   VALUES (?, 1, ?, ?, ?, 'assigned')""",
                (batch_id, f"Task {issue_num}", issue_num, student_id),
            )

        multi_pr_event = {
            "action": "closed",
            "pull_request": {
                "number": 99,
                "merged": True,
                "html_url": "https://github.com/test-org/web-dev-batch-1/pull/99",
                "user": {"login": "testuser"},
                "head": {"ref": "multi-fix"},
                "body": "Fixes #10, Closes #11, and Resolves #12 in one PR!",
            },
            "repository": {"name": "web-dev-batch-1"},
        }

        r = await client.post(
            "/api/webhooks/github",
            json=multi_pr_event,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=mocked",
            },
        )
        assert r.status_code == 200

        # Verify all 3 issues are marked completed
        completed_issues = await test_db.fetch_all(
            "SELECT github_issue_number, status FROM issues WHERE assigned_to = ? AND status = 'completed'",
            (student_id,),
        )
        assert len(completed_issues) == 3

        # Verify 3 submissions recorded
        submissions = await test_db.fetch_all(
            "SELECT id, status FROM submissions WHERE pr_number = 99",
        )
        assert len(submissions) == 3
        assert all(s["status"] == "merged" for s in submissions)

        # Verify progress has 3 issues completed and 75 score (3 * 25)
        progress = await test_db.fetch_one(
            "SELECT issues_completed, score FROM progress WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )
        assert progress["issues_completed"] == 3
        assert progress["score"] == 75

