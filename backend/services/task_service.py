"""
SkillMe — Task Service
Fetches and parses task definitions from the central GitHub repository or local workspace.
"""

import logging
import base64
import re
from pathlib import Path
import yaml
from services.github_service import github_service

logger = logging.getLogger("skillme.task_service")

# Note: Central tasks repo name on GitHub
TASKS_REPO = "SkillMe-Intern-Tasks"


class TaskService:
    """Service to fetch task definitions from local storage or central tasks repo."""

    # Map form display values / synonyms / old slugs → canonical repo folder names
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
        # Lowercase / hyphenated / common synonyms
        "web-dev": "web-dev",
        "web development": "web-dev",
        "web dev": "web-dev",
        "frontend": "web-dev",
        "full stack": "web-dev",
        "python": "python",
        "py": "python",
        "ml": "ml",
        "machine learning": "ml",
        "machine-learning": "ml",
        "ai/ml": "ml",
        "devops": "devops",
        "devops-cloud": "devops",
        "ci-cd": "devops",
        "mobile": "flutter",
        "flutter": "flutter",
        "mobile development": "flutter",
        "ui-ux": "uiux",
        "uiux": "uiux",
        "ui/ux": "uiux",
        "ui/ux design": "uiux",
        "ui ux": "uiux",
        "ui ux design": "uiux",
        "react": "react",
        "react / next.js": "react",
        "react / nextjs": "react",
        "react.js": "react",
        "reactjs": "react",
        "nextjs": "react",
        "node": "node",
        "node.js": "node",
        "nodejs": "node",
        "node.js / express": "node",
        "java": "java",
        "java / spring boot": "java",
        "spring boot": "java",
        "springboot": "java",
        "datascience": "datascience",
        "data-science": "datascience",
        "data science": "datascience",
        "data_science": "datascience",
        "cpp": "cpp",
        "c/c++": "cpp",
        "c++": "cpp",
        "c/c++ / dsa": "cpp",
        "cyber": "cyber",
        "cybersecurity": "cyber",
        "cyber-security": "cyber",
        "cyber security": "cyber",
        "cloud": "cloud",
        "cloud / aws": "cloud",
        "aws": "cloud",
        "dsa": "dsa",
        "dsa / competitive": "dsa",
        "blockchain": "blockchain",
        "blockchain / web3": "blockchain",
        "web3": "blockchain",
        "android": "android",
        "android / kotlin": "android",
        "kotlin": "android",
        "sql": "sql",
        "sql / databases": "sql",
        "databases": "sql",
        "genai": "genai",
        "generative ai": "genai",
        "generative-ai": "genai",
        "gen-ai": "genai",
    }

    def normalize_domain_slug(self, domain: str | None) -> str:
        """
        Robustly convert any domain string (display label, legacy slug, uppercase, etc.)
        into the canonical folder slug used in SkillMe-Intern-Tasks and templates.
        """
        if not domain:
            return "web-dev"

        clean = str(domain).strip()
        # Direct dictionary match
        if clean in self.DOMAIN_SLUG_MAP:
            return self.DOMAIN_SLUG_MAP[clean]

        clean_lower = clean.lower()
        if clean_lower in self.DOMAIN_SLUG_MAP:
            return self.DOMAIN_SLUG_MAP[clean_lower]

        # Alphanumeric check
        alnum = re.sub(r"[^a-z0-9]", "", clean_lower)
        if "datascience" in alnum or "datascien" in alnum:
            return "datascience"
        if "uiux" in alnum or "ui/ux" in clean_lower or "design" in clean_lower:
            return "uiux"
        if "genai" in alnum or "generative" in clean_lower:
            return "genai"
        if "react" in alnum or "next" in clean_lower:
            return "react"
        if "node" in alnum or "express" in clean_lower:
            return "node"
        if "spring" in alnum or "java" in clean_lower:
            return "java"
        if "flutter" in alnum or "mobile" in clean_lower:
            return "flutter"
        if "devops" in alnum or "cicd" in alnum:
            return "devops"
        if "cyber" in alnum or "security" in clean_lower:
            return "cyber"
        if "block" in alnum or "web3" in clean_lower or "crypto" in clean_lower:
            return "blockchain"
        if "android" in alnum or "kotlin" in clean_lower:
            return "android"
        if "sql" in alnum or "database" in clean_lower:
            return "sql"
        if "cpp" in alnum or "c++" in clean_lower or "c/c++" in clean_lower:
            return "cpp"
        if "dsa" in alnum or "algorithm" in clean_lower:
            return "dsa"
        if "aws" in alnum or "cloud" in clean_lower:
            return "cloud"
        if "ml" in alnum or "machinelearning" in clean_lower:
            return "ml"
        if "python" in alnum or "django" in clean_lower or "fastapi" in clean_lower:
            return "python"
        if "web" in alnum or "frontend" in clean_lower or "fullstack" in clean_lower:
            return "web-dev"

        # Fallback sanitized slug
        return re.sub(r"-+", "-", clean_lower.replace(" ", "-").replace("/", "-")).strip("-")

    async def fetch_tasks(self, domain: str, week: int) -> list[dict]:
        """
        Fetch all task markdown files for a given domain and week.
        Checks local filesystem first for instant & reliable loading,
        and falls back to GitHub REST API.
        
        Args:
            domain: e.g. "web-dev", "python", or form display value like "Web Development"
            week: The week number (1-4)
            
        Returns:
            A list of task dictionaries containing title, body, difficulty, and labels.
        """
        slug = self.normalize_domain_slug(domain)
        logger.info(f"Fetching tasks for domain='{domain}' → canonical slug='{slug}', week={week}")

        tasks = []

        # 1. Try reading from local SkillMe-Intern-Tasks directory
        candidate_roots = [
            Path(__file__).resolve().parent.parent.parent / "SkillMe-Intern-Tasks",
            Path.cwd() / "SkillMe-Intern-Tasks",
            Path(__file__).resolve().parent.parent / "SkillMe-Intern-Tasks",
        ]

        local_dir = None
        for root in candidate_roots:
            candidate = root / slug / f"week-{week}"
            if candidate.exists() and candidate.is_dir():
                local_dir = candidate
                break

        if local_dir:
            try:
                md_files = sorted(local_dir.glob("*.md"))
                for file_path in md_files:
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        task_def = self._parse_markdown_task(content, file_path.name)
                        if task_def:
                            tasks.append(task_def)
                    except Exception as fe:
                        logger.warning(f"Failed to read local task file {file_path}: {fe}")
                if tasks:
                    logger.info(f"Loaded {len(tasks)} tasks locally from {local_dir}")
                    tasks.sort(key=lambda x: x.get("_filename", ""))
                    return tasks
            except Exception as e:
                logger.warning(f"Error reading local tasks from {local_dir}: {e}")

        # 2. Fallback: Fetch from GitHub API
        path = f"{slug}/week-{week}"
        logger.info(f"Fetching tasks from GitHub API: {TASKS_REPO}/{path}")
        try:
            res = await github_service.client.get(f"/repos/{github_service.org}/{TASKS_REPO}/contents/{path}")
            if res.status_code == 200:
                contents = res.json()
                if isinstance(contents, list):
                    md_files = [f for f in contents if isinstance(f, dict) and f.get("name", "").endswith(".md")]
                    for f in md_files:
                        file_url = f.get("url")
                        if not file_url:
                            continue
                        file_res = await github_service.client.get(file_url)
                        if file_res.status_code == 200:
                            file_data = file_res.json()
                            if "content" in file_data:
                                content = base64.b64decode(file_data["content"]).decode("utf-8")
                                task_def = self._parse_markdown_task(content, f["name"])
                                if task_def:
                                    tasks.append(task_def)
        except Exception as e:
            logger.warning(f"Error fetching tasks from GitHub repo {TASKS_REPO}/{path}: {e}")

        # 3. Fallback: Provide standard high-quality SkillMe curriculum tasks
        if not tasks:
            logger.warning(f"No tasks found at {path}. Generating default SkillMe curriculum tasks for {domain} Week {week}.")
            domain_name = slug.replace("-", " ").title()
            tasks = [
                {
                    "title": f"Week {week} Task 1: Setup & Architecture for {domain_name}",
                    "body": f"## Objective\nSet up your development environment for **{domain_name}** and familiarize yourself with the project structure.\n\n### Requirements\n1. Clone this repository to your local machine.\n2. Install all necessary dependencies and run the local environment.\n3. Create a new branch named `feature/week-{week}-setup` and add notes to `PROGRESS.md`.\n4. Submit a Pull Request when ready!",
                    "difficulty": "easy",
                    "labels": [f"week-{week}", "easy"],
                    "_filename": "01-setup.md",
                },
                {
                    "title": f"Week {week} Task 2: Core Feature Implementation",
                    "body": f"## Objective\nImplement the primary deliverable for Week {week} in the **{domain_name}** track.\n\n### Requirements\n1. Write clean, modular, and well-documented code.\n2. Ensure error handling and edge cases are covered.\n3. Test your implementation locally.\n4. Push your changes and open a Pull Request linking to this issue.",
                    "difficulty": "medium",
                    "labels": [f"week-{week}", "medium"],
                    "_filename": "02-core-feature.md",
                },
                {
                    "title": f"Week {week} Task 3: Testing & Code Review",
                    "body": f"## Objective\nValidate your implementation with unit/integration tests or code quality checks.\n\n### Requirements\n1. Add test cases or verification steps for your Week {week} code.\n2. Perform a self-review of your PR against industry best practices.\n3. Request a review from the mentor/admin team.",
                    "difficulty": "medium",
                    "labels": [f"week-{week}", "medium"],
                    "_filename": "03-testing.md",
                },
            ]

        # Sort tasks alphabetically by filename (e.g. task-1, task-2)
        tasks.sort(key=lambda x: x.get("_filename", ""))
        return tasks

    def _parse_markdown_task(self, content: str, filename: str) -> dict | None:
        """Parse a markdown file with YAML frontmatter."""
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)", content, re.DOTALL)
        if not match:
            logger.warning(f"No YAML frontmatter found in {filename}")
            title = filename.replace(".md", "").replace("-", " ").title()
            return {
                "title": title,
                "body": content.strip(),
                "difficulty": "medium",
                "labels": [],
                "_filename": filename,
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
            "_filename": filename,
        }


# Global service instance
task_service = TaskService()

