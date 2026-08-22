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

    async def fetch_tasks(self, domain: str, week: int, student_id: int = None) -> list[dict]:
        """
        Fetch task from curriculum.json to serve as the single GitHub issue for the week.
        This unifies the GitHub PR tasks with the UI Dashboard/PDF Curriculum.
        """
        from services.project_curriculum import get_project_track_for_student
        
        project_track = get_project_track_for_student(domain, student_id=student_id)
        
        weeks_dict = project_track.get("weeks", {})
        # Support string or int keys in JSON
        week_data = weeks_dict.get(str(week), weeks_dict.get(week, {}))
        
        title = week_data.get("title", f"Week {week} Project Milestone")
        description = week_data.get("description", "Please refer to your curriculum for task details.")
        
        # Create exactly ONE comprehensive task for this week to replace the disjointed multiple issues
        tasks = [
            {
                "title": f"{title}",
                "body": description,
                "difficulty": "medium",
                "labels": [f"week-{week}"],
                "_filename": "01-capstone.md",
            }
        ]
        
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

