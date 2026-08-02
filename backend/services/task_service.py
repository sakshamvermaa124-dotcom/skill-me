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

    # Map form display values / old slugs → repo folder names
    DOMAIN_SLUG_MAP = {
        # Form display values → repo folder
        "Web Development": "web-dev",
        "Python": "python",
        "Machine Learning": "ml",
        "DevOps / Cloud": "devops",
        "DevOps / CI-CD": "devops",
        "Mobile Development": "flutter",
        "Flutter / Mobile": "flutter",
        "UI/UX Design": "uiux",
        "React / Next.js": "react",
        "Node.js / Express": "node",
        "Java / Spring Boot": "java",
        "Data Science": "datascience",
        "C/C++ / DSA": "cpp",
        "Cybersecurity": "cyber",
        "Cloud / AWS": "cloud",
        "DSA / Competitive": "dsa",
        "DSA / Competitive Programming": "dsa",
        "Blockchain / Web3": "blockchain",
        "Android / Kotlin": "android",
        "SQL / Databases": "sql",
        "Generative AI": "genai",
        # Old short slugs (pass-through)
        "web-dev": "web-dev",
        "python": "python",
        "ml": "ml",
        "devops": "devops",
        "mobile": "flutter",
        "ui-ux": "uiux",
        "react": "react",
        "node": "node",
        "java": "java",
        "datascience": "datascience",
        "cpp": "cpp",
        "cyber": "cyber",
        "cloud": "cloud",
        "dsa": "dsa",
        "blockchain": "blockchain",
        "android": "android",
        "sql": "sql",
        "genai": "genai",
    }

    async def fetch_tasks(self, domain: str, week: int) -> list[dict]:
        """
        Fetch all task markdown files for a given domain and week.
        
        Args:
            domain: e.g. "web-dev", "python", or form display value like "Web Development"
            week: The week number (1-4)
            
        Returns:
            A list of task dictionaries containing title, body, difficulty, and labels.
        """
        # Normalize domain to repo folder slug
        slug = self.DOMAIN_SLUG_MAP.get(domain, domain.lower().replace(" ", "-").replace("/", "-"))
        path = f"{slug}/week-{week}"
        logger.info(f"Fetching tasks from {TASKS_REPO}/{path} (domain='{domain}' → slug='{slug}')")
        
        tasks = []
        try:
            # 1. Get directory contents
            res = await github_service.client.get(f"/repos/{github_service.org}/{TASKS_REPO}/contents/{path}")
            
            if res.status_code == 200:
                contents = res.json()
                if isinstance(contents, list):
                    md_files = [f for f in contents if f["name"].endswith(".md")]
                    for f in md_files:
                        file_res = await github_service.client.get(f["url"])
                        if file_res.status_code == 200:
                            file_data = file_res.json()
                            if "content" in file_data:
                                content = base64.b64decode(file_data["content"]).decode("utf-8")
                                task_def = self._parse_markdown_task(content, f["name"])
                                if task_def:
                                    tasks.append(task_def)
        except Exception as e:
            logger.warning(f"Error fetching tasks from GitHub repo {TASKS_REPO}/{path}: {e}")
                
        # If no tasks found or repo missing, provide standard high-quality SkillMe curriculum tasks
        if not tasks:
            logger.warning(f"No tasks found at {path} in GitHub repo {TASKS_REPO}. Generating default SkillMe curriculum tasks for {domain} Week {week}.")
            domain_name = domain.replace("-", " ").title()
            tasks = [
                {
                    "title": f"Week {week} Task 1: Setup & Architecture for {domain_name}",
                    "body": f"## Objective\nSet up your local development environment for **{domain_name}** and familiarize yourself with the project structure.\n\n### Requirements\n1. Fork and clone this repository to your local machine.\n2. Install all necessary dependencies and run the local dev server/environment.\n3. Create a new branch named `feature/week-{week}-setup` and add an architectural overview or notes to `PROGRESS.md`.\n4. Submit a Pull Request when ready!",
                    "difficulty": "easy",
                    "labels": [f"week-{week}", "easy"],
                    "_filename": "01-setup.md"
                },
                {
                    "title": f"Week {week} Task 2: Core Feature Implementation",
                    "body": f"## Objective\nImplement the primary deliverable for Week {week} in the **{domain_name}** track.\n\n### Requirements\n1. Write clean, modular, and well-documented code.\n2. Ensure error handling and edge cases are covered.\n3. Test your implementation locally.\n4. Push your changes and open a Pull Request linking to this issue.",
                    "difficulty": "medium",
                    "labels": [f"week-{week}", "medium"],
                    "_filename": "02-core-feature.md"
                },
                {
                    "title": f"Week {week} Task 3: Testing & Code Review",
                    "body": f"## Objective\nValidate your implementation with unit/integration tests or code quality checks.\n\n### Requirements\n1. Add test cases or verification steps for your Week {week} code.\n2. Perform a self-review of your PR against industry best practices.\n3. Request a review from the mentor/admin team.",
                    "difficulty": "medium",
                    "labels": [f"week-{week}", "medium"],
                    "_filename": "03-testing.md"
                }
            ]

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
