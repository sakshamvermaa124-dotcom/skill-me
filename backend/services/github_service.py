"""
SkillMe — GitHub Service
Async GitHub API wrapper using httpx.
Handles all interactions with the GitHub organization.
"""

import httpx
import hmac
import hashlib
import logging
from config import settings

logger = logging.getLogger("skillme.github")


class GitHubService:
    """Async GitHub API client for SkillMe automation."""

    def __init__(self):
        self.org = settings.github_org
        self.base_url = settings.github_api_url
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {settings.skillme_github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ──────────────────────────────────────────────
    # Repository Operations
    # ──────────────────────────────────────────────

    async def create_repo_from_template(
        self, template_repo: str, new_repo_name: str, private: bool = False, description: str = ""
    ) -> dict:
        """
        Create a new repository from a template repository.

        Args:
            template_repo: Name of the template repo in the org (e.g., 'web-dev-template')
            new_repo_name: Name for the new repo (e.g., 'web-dev-batch-1')
            private: Whether the repo should be private
            description: Repo description
        """
        response = await self.client.post(
            f"/repos/{self.org}/{template_repo}/generate",
            json={
                "owner": self.org,
                "name": new_repo_name,
                "description": description or f"SkillMe Internship — {new_repo_name}",
                "private": private,
                "include_all_branches": False,
            },
        )
        response.raise_for_status()
        repo_data = response.json()
        logger.info(f"Created repo: {self.org}/{new_repo_name} from template {template_repo}")
        return repo_data

    async def get_repo(self, repo_name: str) -> dict | None:
        """Get repository info. Returns None if not found."""
        response = await self.client.get(f"/repos/{self.org}/{repo_name}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def delete_repo(self, repo_name: str) -> bool:
        """Delete a repository. Use with caution."""
        response = await self.client.delete(f"/repos/{self.org}/{repo_name}")
        if response.status_code == 204:
            logger.warning(f"Deleted repo: {self.org}/{repo_name}")
            return True
        return False

    # ──────────────────────────────────────────────
    # Collaborator Operations
    # ──────────────────────────────────────────────

    async def add_collaborator(
        self, repo_name: str, username: str, permission: str = "push"
    ) -> dict:
        """
        Add a user as a collaborator to a repo.

        Args:
            repo_name: Repository name
            username: GitHub username to invite
            permission: One of 'pull', 'push', 'admin', 'maintain', 'triage'
        """
        clean_user = (username or "").strip()
        if "github.com/" in clean_user:
            clean_user = clean_user.rstrip("/").split("/")[-1]
        clean_user = clean_user.lstrip("@").strip()
        if not clean_user:
            raise ValueError("Invalid GitHub username for collaborator invitation")

        response = await self.client.put(
            f"/repos/{self.org}/{repo_name}/collaborators/{clean_user}",
            json={"permission": permission},
        )
        response.raise_for_status()
        logger.info(f"Added {clean_user} as collaborator to {repo_name} with {permission} access")
        # 201 = invitation created, 204 = already a collaborator
        if response.status_code == 201:
            return response.json()
        return {"status": "already_collaborator"}

    async def remove_collaborator(self, repo_name: str, username: str) -> bool:
        """Remove a collaborator from a repo."""
        clean_user = (username or "").strip()
        if "github.com/" in clean_user:
            clean_user = clean_user.rstrip("/").split("/")[-1]
        clean_user = clean_user.lstrip("@").strip()

        try:
            response = await self.client.delete(
                f"/repos/{self.org}/{repo_name}/collaborators/{clean_user}"
            )
            response.raise_for_status()
            logger.info(f"Removed {clean_user} from {repo_name}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            logger.error(f"Failed to remove collaborator {username} from {repo_name}: {e}")
            raise

    async def check_collaborator(self, repo_name: str, username: str) -> bool:
        """Check if a user is currently a collaborator on a repo."""
        clean_user = (username or "").strip()
        if not clean_user:
            return False
        
        response = await self.client.get(
            f"/repos/{self.org}/{repo_name}/collaborators/{clean_user}"
        )
        if response.status_code == 204:
            return True
        elif response.status_code == 404:
            return False
            
        logger.warning(f"Unexpected status code {response.status_code} checking collaborator {username} on {repo_name}")
        return False

    # ──────────────────────────────────────────────
    # Issue Operations
    # ──────────────────────────────────────────────

    async def create_issue(
        self,
        repo_name: str,
        title: str,
        body: str = "",
        assignee: str | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """
        Create a GitHub issue in a repo.

        Args:
            repo_name: Repository name
            title: Issue title
            body: Issue body (markdown)
            assignee: GitHub username to assign (must be a collaborator)
            labels: List of label names
        """
        payload = {"title": title, "body": body}
        if assignee:
            clean_assignee = assignee.strip()
            if "github.com/" in clean_assignee:
                clean_assignee = clean_assignee.rstrip("/").split("/")[-1]
            clean_assignee = clean_assignee.lstrip("@").strip()
            if clean_assignee:
                payload["assignees"] = [clean_assignee]
        if labels:
            payload["labels"] = labels

        response = await self.client.post(
            f"/repos/{self.org}/{repo_name}/issues",
            json=payload,
        )
        response.raise_for_status()
        issue_data = response.json()
        logger.info(f"Created issue #{issue_data['number']}: {title} in {repo_name}")
        return issue_data

    async def get_issue(self, repo_name: str, issue_number: int) -> dict | None:
        """Get an issue by number."""
        response = await self.client.get(
            f"/repos/{self.org}/{repo_name}/issues/{issue_number}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def close_issue(self, repo_name: str, issue_number: int) -> dict:
        """Close an issue."""
        response = await self.client.patch(
            f"/repos/{self.org}/{repo_name}/issues/{issue_number}",
            json={"state": "closed"},
        )
        response.raise_for_status()
        return response.json()

    async def add_assignees_to_issue(
        self, repo_name: str, issue_number: int, assignees: list[str]
    ) -> dict:
        """
        Add assignees to an existing GitHub issue.

        Args:
            repo_name: Repository name
            issue_number: The GitHub issue number
            assignees: List of GitHub usernames to assign

        Returns the updated issue data, or an empty dict if the request failed.
        """
        response = await self.client.post(
            f"/repos/{self.org}/{repo_name}/issues/{issue_number}/assignees",
            json={"assignees": assignees},
        )
        response.raise_for_status()
        logger.info(
            f"Added assignees {assignees} to issue #{issue_number} in {repo_name}"
        )
        return response.json()

    async def list_issues(
        self, repo_name: str, state: str = "open", labels: str | None = None
    ) -> list[dict]:
        """List issues in a repo."""
        params = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = labels
        response = await self.client.get(
            f"/repos/{self.org}/{repo_name}/issues", params=params
        )
        response.raise_for_status()
        return response.json()

    # ──────────────────────────────────────────────
    # Pull Request Operations
    # ──────────────────────────────────────────────

    async def list_pull_requests(
        self, repo_name: str, state: str = "open"
    ) -> list[dict]:
        """List pull requests in a repo."""
        response = await self.client.get(
            f"/repos/{self.org}/{repo_name}/pulls",
            params={"state": state, "per_page": 100},
        )
        response.raise_for_status()
        return response.json()

    async def get_pull_request(self, repo_name: str, pr_number: int) -> dict | None:
        """Get a specific pull request."""
        response = await self.client.get(
            f"/repos/{self.org}/{repo_name}/pulls/{pr_number}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def merge_pull_request(
        self, repo_name: str, pr_number: int, merge_method: str = "squash"
    ) -> dict:
        """Merge a pull request."""
        response = await self.client.put(
            f"/repos/{self.org}/{repo_name}/pulls/{pr_number}/merge",
            json={"merge_method": merge_method},
        )
        response.raise_for_status()
        logger.info(f"Merged PR #{pr_number} in {repo_name}")
        return response.json()

    async def add_pr_comment(
        self, repo_name: str, pr_number: int, body: str
    ) -> dict:
        """Add a comment to a pull request (via issues API)."""
        response = await self.client.post(
            f"/repos/{self.org}/{repo_name}/issues/{pr_number}/comments",
            json={"body": body},
        )
        response.raise_for_status()
        return response.json()

    # ──────────────────────────────────────────────
    # Webhook Operations
    # ──────────────────────────────────────────────

    async def create_webhook(
        self, repo_name: str, webhook_url: str, events: list[str] | None = None
    ) -> dict:
        """
        Create a webhook on a repo.

        Args:
            repo_name: Repository name
            webhook_url: URL that GitHub will POST events to
            events: List of events to subscribe to (default: pull_request, check_suite)
        """
        if events is None:
            events = ["pull_request", "check_suite", "issues"]

        response = await self.client.post(
            f"/repos/{self.org}/{repo_name}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": events,
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": settings.webhook_secret,
                    "insecure_ssl": "0",
                },
            },
        )
        response.raise_for_status()
        logger.info(f"Created webhook on {repo_name} → {webhook_url}")
        return response.json()

    # ──────────────────────────────────────────────
    # User Operations
    # ──────────────────────────────────────────────

    async def get_user(self, username: str) -> dict | None:
        """Get a GitHub user's profile."""
        response = await self.client.get(f"/users/{username}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def verify_token(self) -> dict | None:
        """Verify the configured GitHub token works."""
        response = await self.client.get("/user")
        if response.status_code == 200:
            return response.json()
        return None

    # ──────────────────────────────────────────────
    # Webhook Verification
    # ──────────────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """
        Verify that a webhook payload was sent by GitHub.

        Args:
            payload: Raw request body
            signature: The X-Hub-Signature-256 header value
        """
        if not settings.webhook_secret:
            return True  # Skip verification if no secret configured

        expected = "sha256=" + hmac.new(
            settings.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


# Global service instance
github_service = GitHubService()
