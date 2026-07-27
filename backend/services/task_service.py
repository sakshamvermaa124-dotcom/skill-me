"""
SkillMe — Task Service
Fetches and parses task definitions from the central GitHub repository.
"""

import logging
import base64
import re
import yaml
from services.github_service import github_service

logger = logging.getLogger("skillme.task_service")

# Note: We hardcode the repo name here as agreed in the plan.
TASKS_REPO = "SkillMe-Intern-Tasks"

class TaskService:
    """Service to fetch task definitions from the central tasks repo."""

    async def fetch_tasks(self, domain: str, week: int) -> list[dict]:
        """
        Fetch all task markdown files for a given domain and week.
        
        Args:
            domain: e.g. "web-dev", "python"
            week: The week number (1-4)
            
        Returns:
            A list of task dictionaries containing title, body, difficulty, and labels.
        """
        path = f"{domain}/week-{week}"
        logger.info(f"Fetching tasks from {TASKS_REPO}/{path}")
        
        # 1. Get directory contents
        res = await github_service.client.get(f"/repos/{github_service.org}/{TASKS_REPO}/contents/{path}")
        
        if res.status_code == 404:
            logger.warning(f"No tasks found at {path}")
            return []
            
        res.raise_for_status()
        contents = res.json()
        
        if not isinstance(contents, list):
            # It's a file, not a directory
            logger.warning(f"Expected directory at {path}, found file")
            return []
            
        # 2. Filter for markdown files
        md_files = [f for f in contents if f["name"].endswith(".md")]
        
        tasks = []
        # 3. Fetch and parse each file
        for f in md_files:
            file_res = await github_service.client.get(f["url"])
            if file_res.status_code != 200:
                continue
                
            file_data = file_res.json()
            if "content" not in file_data:
                continue
                
            # Decode base64 content
            content = base64.b64decode(file_data["content"]).decode("utf-8")
            
            # Parse YAML frontmatter
            task_def = self._parse_markdown_task(content, f["name"])
            if task_def:
                tasks.append(task_def)
                
        # Sort tasks alphabetically by filename (e.g. task-1, task-2)
        tasks.sort(key=lambda x: x.get("_filename", ""))
        
        return tasks
        
    def _parse_markdown_task(self, content: str, filename: str) -> dict | None:
        """Parse a markdown file with YAML frontmatter."""
        # Split frontmatter and body
        match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if not match:
            logger.warning(f"No YAML frontmatter found in {filename}")
            # Fallback: use filename as title and entire content as body
            title = filename.replace(".md", "").replace("-", " ").title()
            return {
                "title": title,
                "body": content.strip(),
                "difficulty": "medium",
                "labels": [],
                "_filename": filename
            }
            
        frontmatter_str, match_body = match.groups()
        
        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML in {filename}: {e}")
            frontmatter = {}
            
        title = frontmatter.get("title", filename.replace(".md", "").replace("-", " ").title())
        difficulty = frontmatter.get("difficulty", "medium")
        labels = frontmatter.get("labels", [])
        
        return {
            "title": title,
            "body": match_body.strip(),
            "difficulty": difficulty,
            "labels": labels,
            "_filename": filename
        }

# Global service instance
task_service = TaskService()
