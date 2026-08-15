"""
SkillMe — Batch Service
Orchestrates the batch lifecycle: creation, student enrollment,
issue assignment, and progress tracking.
"""

import logging
import re
from datetime import datetime, timedelta
from db.database import db
from services.github_service import github_service
from services.task_service import task_service
from config import settings

logger = logging.getLogger("skillme.batch")

# Issue templates per week (domain-agnostic structure)
# These are overridden by domain-specific templates in the template repos
WEEK_LABELS = {
    1: {"label": "week-1", "difficulty": "easy", "prefix": "Week 1"},
    2: {"label": "week-2", "difficulty": "easy", "prefix": "Week 2"},
    3: {"label": "week-3", "difficulty": "medium", "prefix": "Week 3"},
    4: {"label": "week-4", "difficulty": "hard", "prefix": "Week 4"},
}


class BatchService:
    """Manages the full batch lifecycle."""

    # ──────────────────────────────────────────────
    # Batch CRUD
    # ──────────────────────────────────────────────

    async def create_batch(
        self,
        domain: str,
        batch_number: int,
        template_repo: str | None = None,
        max_students: int = 30,
        start_date: str | None = None,
        webhook_url: str | None = None,
    ) -> dict:
        """
        Create a new batch:
        1. Generate a GitHub repo from the domain's template
        2. Set up a webhook for PR events
        3. Insert the batch record into the database

        Args:
            domain: Domain name (e.g., 'web-dev', 'python')
            batch_number: Sequential batch number
            template_repo: Template repo name (defaults to '{domain}-template')
            max_students: Maximum students in this batch
            start_date: ISO date string for batch start
            webhook_url: URL for GitHub webhooks
        """
        template = template_repo or f"{domain}-template"
        repo_name = f"{domain}-batch-{batch_number}"

        # Check if batch already exists in DB
        existing = await db.fetch_one(
            "SELECT id FROM batches WHERE domain = ? AND batch_number = ?",
            (domain, batch_number),
        )
        if existing:
            raise ValueError(f"Batch {domain} #{batch_number} already exists (id={existing['id']})")

        # Create GitHub repo — try domain template first, then generic fallbacks.
        # We do NOT silently swallow a full failure; the return value will surface it.
        github_repo_created = False
        FALLBACK_TEMPLATES = [template, "ml-template", "web-dev-template"]

        existing_repo = None
        try:
            existing_repo = await github_service.get_repo(repo_name)
        except Exception as e:
            logger.warning(f"GitHub get_repo failed for {repo_name}: {e}")

        if existing_repo:
            logger.warning(f"Repo {repo_name} already exists on GitHub, using existing")
            github_repo_created = True
        else:
            for tmpl in FALLBACK_TEMPLATES:
                try:
                    await github_service.create_repo_from_template(
                        template_repo=tmpl,
                        new_repo_name=repo_name,
                        description=f"SkillMe {domain.replace('-', ' ').title()} Internship — Batch {batch_number}",
                    )
                    github_repo_created = True
                    if tmpl != template:
                        logger.warning(
                            f"Domain template '{template}' not found. "
                            f"Used fallback '{tmpl}' to create {repo_name}."
                        )
                    break
                except Exception as e:
                    logger.warning(f"Template '{tmpl}' failed for {repo_name}: {e}")

            if not github_repo_created:
                logger.error(
                    f"All templates failed for {repo_name}. "
                    f"Batch will be created in DB but has NO GitHub repo — "
                    f"enrollment and task assignment will fail until the repo is created manually."
                )

        github_webhook_created = False
        # Resolve the webhook URL: prefer the explicitly passed value, then
        # auto-build from BACKEND_URL env var so admins don't have to type it.
        resolved_webhook_url = webhook_url
        if not resolved_webhook_url and settings.backend_url:
            resolved_webhook_url = settings.backend_url.rstrip("/") + "/api/webhooks/github"
            logger.info(f"Auto-derived webhook URL: {resolved_webhook_url}")

        if resolved_webhook_url:
            try:
                await github_service.create_webhook(repo_name, resolved_webhook_url)
                github_webhook_created = True
                logger.info(f"Webhook registered on {repo_name} → {resolved_webhook_url}")
            except Exception as e:
                logger.error(f"Failed to create webhook for {repo_name}: {e}")

        # Calculate dates
        if not start_date:
            start_date = datetime.utcnow().strftime("%Y-%m-%d")
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d") + timedelta(weeks=4)
        ).strftime("%Y-%m-%d")

        # Insert into database
        batch_id = await db.insert(
            """INSERT INTO batches (domain, batch_number, repo_name, status, max_students, start_date, end_date)
               VALUES (?, ?, ?, 'active', ?, ?, ?)""",
            (domain, batch_number, repo_name, max_students, start_date, end_date),
        )

        logger.info(f"Created batch: {domain} #{batch_number} (id={batch_id}, repo={repo_name}, github_repo_created={github_repo_created})")

        return {
            "id": batch_id,
            "domain": domain,
            "batch_number": batch_number,
            "repo_name": repo_name,
            "status": "active",
            "start_date": start_date,
            "end_date": end_date,
            "github_repo_created": github_repo_created,
            "github_webhook_created": github_webhook_created,
        }


    async def get_batch(self, batch_id: int) -> dict | None:
        """Get a batch by ID."""
        return await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))

    async def list_batches(self, status: str | None = None) -> list[dict]:
        """List all batches, optionally filtered by status."""
        if status:
            return await db.fetch_all(
                "SELECT * FROM batches WHERE status = ? ORDER BY created_at DESC", (status,)
            )
        return await db.fetch_all("SELECT * FROM batches ORDER BY created_at DESC")

    async def update_batch_status(self, batch_id: int, status: str) -> bool:
        """Update batch status."""
        await db.execute(
            "UPDATE batches SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, batch_id),
        )
        return True

    # ──────────────────────────────────────────────
    # Student Enrollment
    # ──────────────────────────────────────────────

    async def add_student_to_batch(self, student_id: int, batch_id: int) -> dict:
        """
        Enroll a student in a batch:
        1. Add them as a GitHub collaborator
        2. Create the enrollment record

        Args:
            student_id: Student database ID
            batch_id: Batch database ID
        """
        # Get student and batch info
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            raise ValueError(f"Student {student_id} not found")

        batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        # Check enrollment count
        enrolled_count = await db.fetch_one(
            "SELECT COUNT(*) as count FROM enrollments WHERE batch_id = ? AND status != 'dropped'",
            (batch_id,),
        )
        if enrolled_count and enrolled_count["count"] >= batch["max_students"]:
            raise ValueError(f"Batch {batch_id} is full ({batch['max_students']} students max)")

        # Check if already enrolled
        existing = await db.fetch_one(
            "SELECT id FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )
        if existing:
            raise ValueError(f"Student {student_id} is already enrolled in batch {batch_id}")

        # Add as GitHub collaborator
        invite_status = "pending"
        if student["github_username"] and batch["repo_name"]:
            try:
                await github_service.add_collaborator(
                    batch["repo_name"], student["github_username"]
                )
                invite_status = "accepted"  # Optimistic — GitHub sends an invite
            except Exception as e:
                logger.error(f"Failed to add {student['github_username']} to {batch['repo_name']}: {e}")
                invite_status = "failed"

        # Create enrollment
        enrollment_id = await db.insert(
            """INSERT INTO enrollments (student_id, batch_id, status, github_invite_status)
               VALUES (?, ?, 'enrolled', ?)""",
            (student_id, batch_id, invite_status),
        )

        # Update student status
        await db.execute(
            "UPDATE students SET status = 'enrolled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (student_id,),
        )

        logger.info(
            f"Enrolled student {student['first_name']} {student['last_name']} "
            f"(id={student_id}) in batch {batch['domain']} #{batch['batch_number']}"
        )

        # Automatically assign tasks only for weeks the admin has explicitly assigned previously.
        # Do NOT default to Week 1 — issue assignment must always be triggered manually by the admin.
        import json
        try:
            weeks_to_assign = json.loads(batch.get("weeks_assigned") or "[]")
            for w in weeks_to_assign:
                logger.info(f"Auto-assigning Week {w} tasks for newly enrolled student {student_id}")
                created = await self.assign_week_from_task_repo(batch_id=batch_id, week_number=w)
                if created:
                    from services.email_service import email_service
                    import asyncio
                    from config import settings
                    base_repo_url = f"https://github.com/{settings.github_org}/{batch['repo_name']}" if batch.get("repo_name") else None
                    gh_user = student.get("github_username")
                    tasks_for_email = [
                        {
                            "title": r.get("title", "Task"), 
                            "issue_url": f"{base_repo_url}/issues/{r.get('github_issue_number')}" if r.get("github_issue_number") else base_repo_url
                        }
                        for r in created if r.get("assigned_to") == student_id
                    ]
                    if tasks_for_email:
                        asyncio.create_task(
                            email_service.send_weekly_tasks_notification(
                                first_name=student["first_name"],
                                last_name=student["last_name"],
                                email=student["email"],
                                domain=batch["domain"],
                                batch_number=batch["batch_number"],
                                week_number=w,
                                tasks=tasks_for_email,
                                repo_url=base_repo_url,
                                github_username=gh_user or None,
                            )
                        )
        except Exception as e:
            logger.warning(f"Could not auto-assign tasks on enrollment for student {student_id}: {e}")

        return {
            "enrollment_id": enrollment_id,
            "student_id": student_id,
            "batch_id": batch_id,
            "github_invite_status": invite_status,
        }

    async def auto_enroll_student(self, student_id: int) -> dict:
        """
        Automated 1-repo-per-student enrollment:
        1. Validates student and GitHub username.
        2. Determines domain slug and unique student repository name.
        3. Creates personal repository from domain template.
        4. Registers GitHub webhook on the new repository.
        5. Adds student as collaborator with push permissions.
        6. Creates dedicated batch record in DB and enrolls student.
        7. Auto-assigns Week 1 tasks from central tasks repo.
        """
        # 1. Fetch student
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            raise ValueError(f"Student #{student_id} not found")

        # 2. Check if already actively enrolled
        existing = await db.fetch_one(
            """SELECT e.id, e.batch_id, b.repo_name, b.domain, b.batch_number 
               FROM enrollments e 
               JOIN batches b ON e.batch_id = b.id 
               WHERE e.student_id = ? AND e.status != 'dropped'""",
            (student_id,),
        )
        if existing:
            raise ValueError(
                f"Student is already enrolled in {existing['domain']} Batch #{existing['batch_number']} "
                f"(Repository: {existing['repo_name']})"
            )

        # 3. Check GitHub username
        raw_gh = (student.get("github_username") or "").strip()
        if "github.com/" in raw_gh:
            raw_gh = raw_gh.rstrip("/").split("/")[-1]
        raw_gh = raw_gh.lstrip("@").strip()
        if not raw_gh:
            raise ValueError("Student has no GitHub username specified. Please update their profile before enrolling.")
        
        # Clean username for repo naming
        gh_clean = re.sub(r"[^a-zA-Z0-9_-]", "", raw_gh.lower())
        if not gh_clean:
            gh_clean = f"student-{student_id}"

        # 4. Resolve domain and slug
        raw_domain = student.get("domain") or "web-dev"
        slug = task_service.DOMAIN_SLUG_MAP.get(raw_domain, raw_domain.lower().replace(" ", "-").replace("/", "-"))

        # Determine next batch number for this domain
        batch_count_row = await db.fetch_one(
            "SELECT COALESCE(MAX(batch_number), 0) + 1 AS next_batch FROM batches WHERE domain = ?",
            (slug,),
        )
        batch_number = batch_count_row["next_batch"] if batch_count_row else 1

        # Formulate unique repo name: e.g. web-dev-sakshamvermaa124
        # If collision exists, use web-dev-b{batch_number}-sakshamvermaa124
        repo_name = f"{slug}-{gh_clean}"
        existing_batch_repo = await db.fetch_one("SELECT id FROM batches WHERE repo_name = ?", (repo_name,))
        if existing_batch_repo:
            repo_name = f"{slug}-b{batch_number}-{gh_clean}"

        # 5. Create GitHub Repository from Template
        template_name = f"{slug}-template"
        FALLBACK_TEMPLATES = [template_name, "web-dev-template", "ml-template"]
        github_repo_created = False

        existing_repo = None
        try:
            existing_repo = await github_service.get_repo(repo_name)
        except Exception as e:
            logger.warning(f"GitHub get_repo check failed for {repo_name}: {e}")

        if existing_repo:
            logger.warning(f"Repo {repo_name} already exists on GitHub, reusing existing repo")
            github_repo_created = True
        else:
            for tmpl in FALLBACK_TEMPLATES:
                try:
                    await github_service.create_repo_from_template(
                        template_repo=tmpl,
                        new_repo_name=repo_name,
                        description=f"SkillMe {raw_domain} Internship — {student['first_name']} {student['last_name']} (@{raw_gh})",
                    )
                    github_repo_created = True
                    break
                except Exception as e:
                    logger.warning(f"Template '{tmpl}' failed for {repo_name}: {e}")

        # 6. Configure Webhook on new repository
        github_webhook_created = False
        resolved_webhook_url = None
        if settings.backend_url:
            resolved_webhook_url = settings.backend_url.rstrip("/") + "/api/webhooks/github"
            try:
                await github_service.create_webhook(repo_name, resolved_webhook_url)
                github_webhook_created = True
                logger.info(f"Webhook registered on {repo_name} → {resolved_webhook_url}")
            except Exception as e:
                logger.error(f"Failed to create webhook for {repo_name}: {e}")

        # 7. Add Student as Collaborator
        invite_status = "pending"
        try:
            await github_service.add_collaborator(repo_name, raw_gh, permission="push")
            invite_status = "accepted"
        except Exception as e:
            logger.error(f"Failed to add {raw_gh} as collaborator to {repo_name}: {e}")
            invite_status = "failed"

        # 8. Create Batch in DB (1 student capacity for dedicated repo)
        start_date = datetime.utcnow().strftime("%Y-%m-%d")
        end_date = (datetime.utcnow() + timedelta(weeks=4)).strftime("%Y-%m-%d")

        batch_id = await db.insert(
            """INSERT INTO batches (domain, batch_number, repo_name, status, max_students, start_date, end_date, auto_assign)
               VALUES (?, ?, ?, 'active', 1, ?, ?, 0)""",
            (slug, batch_number, repo_name, start_date, end_date),
        )

        # 9. Create Enrollment Record
        enrollment_id = await db.insert(
            """INSERT INTO enrollments (student_id, batch_id, status, github_invite_status)
               VALUES (?, ?, 'enrolled', ?)""",
            (student_id, batch_id, invite_status),
        )

        # Update student status to 'enrolled'
        await db.execute(
            "UPDATE students SET status = 'enrolled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (student_id,),
        )

        logger.info(
            f"Auto-enrolled student {student['first_name']} {student['last_name']} "
            f"(id={student_id}) into dedicated batch {slug} #{batch_number} (repo: {repo_name})"
        )

        # 10. Automatically assign Week 1 tasks into their new repo
        created_tasks = []
        try:
            created_tasks = await self.assign_week_from_task_repo(batch_id=batch_id, week_number=1)
            logger.info(f"Auto-assigned {len(created_tasks)} Week 1 tasks for student {student_id} in {repo_name}")
        except Exception as e:
            logger.warning(f"Could not auto-assign Week 1 tasks for student {student_id}: {e}")

        repo_url = f"https://github.com/{github_service.org}/{repo_name}"

        return {
            "enrollment_id": enrollment_id,
            "student_id": student_id,
            "batch_id": batch_id,
            "domain": slug,
            "batch_number": batch_number,
            "repo_name": repo_name,
            "repo_url": repo_url,
            "github_repo_created": github_repo_created,
            "github_webhook_created": github_webhook_created,
            "github_invite_status": invite_status,
            "week_1_tasks": created_tasks,
        }

    async def remove_student_from_batch(self, student_id: int, batch_id: int) -> bool:
        """Remove a student from a batch and revoke GitHub access."""
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))

        if student and batch and student["github_username"] and batch["repo_name"]:
            try:
                await github_service.remove_collaborator(
                    batch["repo_name"], student["github_username"]
                )
            except Exception as e:
                logger.error(f"Failed to remove collaborator: {e}")

        await db.execute(
            "UPDATE enrollments SET status = 'dropped' WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )
        return True

    # ──────────────────────────────────────────────
    # Issue Assignment
    # ──────────────────────────────────────────────

    async def assign_week_from_task_repo(self, batch_id: int, week_number: int) -> list[dict]:
        """
        Fetch tasks from the central task repo for the batch's domain and week,
        and assign them to all enrolled students.
        """
        batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        # 1. Fetch tasks for this domain and week
        tasks = await task_service.fetch_tasks(batch["domain"], week_number)
        if not tasks:
            raise ValueError(f"No tasks found for {batch['domain']} week {week_number} in tasks repo.")

        # 2. Get enrolled students who haven't received tasks for this week yet
        enrollments = await db.fetch_all(
            """SELECT e.student_id FROM enrollments e 
               WHERE e.batch_id = ? AND e.status IN ('enrolled', 'active')
               AND NOT EXISTS (
                   SELECT 1 FROM issues i WHERE i.batch_id = e.batch_id AND i.week_number = ? AND i.assigned_to = e.student_id
               )""",
            (batch_id, week_number),
        )
        if not enrollments:
            logger.info(f"All active students in batch {batch_id} already have Week {week_number} tasks.")
            return []

        # 3. Build issue list (each student gets the same set of tasks)
        issues_to_assign = []
        for enrollment in enrollments:
            for task in tasks:
                issues_to_assign.append({
                    "title": task["title"],
                    "body": task["body"],
                    "assigned_to_student_id": enrollment["student_id"],
                })

        # 4. Assign using existing logic
        created = await self.assign_weekly_issues(batch_id, week_number, issues_to_assign)

        # 5. Update weeks_assigned on the batch if not already present
        import json
        try:
            current_weeks = json.loads(batch.get("weeks_assigned") or "[]")
            if week_number not in current_weeks:
                current_weeks.append(week_number)
                current_weeks.sort()
                await db.execute(
                    "UPDATE batches SET weeks_assigned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(current_weeks), batch_id),
                )
        except Exception as e:
            logger.warning(f"Failed to update weeks_assigned for batch {batch_id}: {e}")

        return created

    async def assign_weekly_issues(
        self,
        batch_id: int,
        week_number: int,
        issues: list[dict],
    ) -> list[dict]:
        """
        Create and assign issues for a specific week.

        Each issue dict should have:
        - title: str
        - body: str (markdown description of the task)
        - assigned_to_student_id: int (student database ID)

        Args:
            batch_id: Batch database ID
            week_number: Week number (1-4)
            issues: List of issue definitions
        """
        batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        week_info = WEEK_LABELS.get(week_number, {"label": f"week-{week_number}", "difficulty": "medium", "prefix": f"Week {week_number}"})
        created_issues = []

        for issue_def in issues:
            student_id = issue_def.get("assigned_to_student_id")
            student = None
            assignee_username = None

            # Task assignment deduplication guard: skip creating duplicate GitHub issues if already assigned
            if student_id:
                existing_issue = await db.fetch_one(
                    """SELECT id, github_issue_number FROM issues 
                       WHERE batch_id = ? AND week_number = ? AND assigned_to = ? AND title = ?""",
                    (batch_id, week_number, student_id, issue_def["title"])
                )
                if existing_issue:
                    logger.info(f"Skipping duplicate task assignment '{issue_def['title']}' for student {student_id} in batch {batch_id}.")
                    created_issues.append({
                        "id": existing_issue["id"],
                        "github_issue_number": existing_issue["github_issue_number"],
                        "title": issue_def["title"],
                        "assigned_to": student_id,
                        "week": week_number,
                    })
                    continue

            if student_id:
                student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
                if student:
                    assignee_username = student.get("github_username")

            # Create issue on GitHub
            title = f"[{week_info['prefix']}] {issue_def['title']}"
            body = issue_def.get("body", "")

            try:
                gh_issue = await github_service.create_issue(
                    repo_name=batch["repo_name"],
                    title=title,
                    body=body,
                    assignee=assignee_username,
                    labels=[week_info["label"], week_info["difficulty"]],
                )
                github_issue_number = gh_issue["number"]
            except Exception as e:
                logger.error(f"Failed to create GitHub issue with assignee {assignee_username}: {e}")
                # Retry without assignee (e.g. if student hasn't accepted invite yet)
                if assignee_username:
                    try:
                        logger.info(f"Retrying issue creation without assignee...")
                        gh_issue = await github_service.create_issue(
                            repo_name=batch["repo_name"],
                            title=title,
                            body=body,
                            assignee=None,
                            labels=[week_info["label"], week_info["difficulty"]],
                        )
                        github_issue_number = gh_issue["number"]
                    except Exception as fallback_e:
                        logger.error(f"Failed to create GitHub issue without assignee: {fallback_e}")
                        github_issue_number = None
                else:
                    github_issue_number = None

            if github_issue_number is None:
                logger.error(f"Skipping database insertion for task '{title}' because GitHub issue creation failed.")
                continue

            # Record in database
            issue_id = await db.insert(
                """INSERT INTO issues (batch_id, github_issue_number, title, description, week_number, difficulty, assigned_to, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    github_issue_number,
                    issue_def["title"],
                    body,
                    week_number,
                    week_info["difficulty"],
                    student_id,
                    "assigned" if student_id else "open",
                ),
            )

            # Initialize/update progress record
            if student_id:
                existing_progress = await db.fetch_one(
                    "SELECT id, issues_assigned FROM progress WHERE student_id = ? AND batch_id = ? AND week = ?",
                    (student_id, batch_id, week_number),
                )
                if existing_progress:
                    await db.execute(
                        "UPDATE progress SET issues_assigned = issues_assigned + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (existing_progress["id"],),
                    )
                else:
                    await db.insert(
                        "INSERT INTO progress (student_id, batch_id, week, issues_assigned) VALUES (?, ?, ?, 1)",
                        (student_id, batch_id, week_number),
                    )

            created_issues.append({
                "id": issue_id,
                "github_issue_number": github_issue_number,
                "title": issue_def["title"],
                "assigned_to": student_id,
                "week": week_number,
            })

        logger.info(f"Assigned {len(created_issues)} issues for batch {batch_id}, week {week_number}")
        return created_issues

    # ──────────────────────────────────────────────
    # Progress Tracking
    # ──────────────────────────────────────────────

    async def record_submission(
        self,
        batch_id: int,
        student_github_username: str,
        pr_number: int,
        pr_url: str,
        pr_head_branch: str | None = None,
        pr_body: str | None = None,
    ) -> dict | None:
        """
        Record a PR submission from a student.
        Called by the webhook handler when a PR is opened.

        Args:
            batch_id: Batch database ID
            student_github_username: GitHub username from the PR author
            pr_number: GitHub PR number
            pr_url: Full URL to the pull request
            pr_head_branch: The branch name of the PR head (e.g. '7-build-navbar').
            pr_body: The PR description text. Checked for closing keywords like
                     'Fixes #7', 'Closes #7', 'Resolves #7'.
        """
        # Find the student
        student = await db.fetch_one(
            "SELECT * FROM students WHERE LOWER(github_username) = LOWER(?)",
            (student_github_username,),
        )
        if not student:
            logger.warning(f"Unknown student GitHub user: {student_github_username}")
            return None

        # Find the enrollment
        enrollment = await db.fetch_one(
            "SELECT * FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (student["id"], batch_id),
        )
        if not enrollment:
            logger.warning(f"Student {student_github_username} not enrolled in batch {batch_id}")
            return None

        # ── Issue Resolution: 4-strategy cascade ─────────────────────────────
        # Each strategy is tried in order. We stop at the first successful match.
        # This makes PR→issue linking robust against non-standard branch names.
        issue = None
        match_strategy = None

        matched_issues = []
        match_strategies = []

        # Strategy 1: Branch prefix matches github_issue_number exactly.
        if pr_head_branch:
            parts = pr_head_branch.split("-", 1)
            if parts[0].isdigit():
                linked_issue_number = int(parts[0])
                issue = await db.fetch_one(
                    """SELECT * FROM issues
                       WHERE batch_id = ? AND assigned_to = ? AND github_issue_number = ?
                       LIMIT 1""",
                    (batch_id, student["id"], linked_issue_number),
                )
                if issue:
                    matched_issues.append(issue)
                    match_strategies.append(f"branch-prefix #{linked_issue_number}")

        # Strategy 2: PR title keyword match against issue titles.
        # Only run if no matches yet.
        if not matched_issues and pr_head_branch:
            pr_slug = pr_head_branch.lower().replace("-", " ").replace("_", " ")
            open_issues = await db.fetch_all(
                """SELECT * FROM issues
                   WHERE batch_id = ? AND assigned_to = ? AND status IN ('assigned', 'open', 'in_progress')
                   ORDER BY week_number ASC""",
                (batch_id, student["id"]),
            )
            best_score = 0
            best_issue = None
            stop_words = {"a", "an", "the", "with", "and", "or", "of", "to", "in",
                          "for", "on", "by", "at", "is", "it", "week", "build",
                          "create", "add", "feat", "feature", "week1", "week2",
                          "week3", "week4"}
            pr_words = {w for w in pr_slug.split() if w not in stop_words and len(w) > 2}
            for candidate in open_issues:
                title_words = {
                    w for w in candidate["title"].lower().replace("-", " ").split()
                    if w not in stop_words and len(w) > 2
                }
                score = len(pr_words & title_words)
                if score > best_score:
                    best_score = score
                    best_issue = candidate
            if best_issue and best_score >= 2:
                matched_issues.append(best_issue)
                match_strategies.append(f"title-keyword-match (score={best_score}, issue #{best_issue['github_issue_number']})")

        # Strategy 3: PR body closing keyword — looks for "Fixes #N", "Closes #N",
        # "Resolves #N" in the PR description. We ALWAYS run this because a single
        # PR can close multiple issues.
        if pr_body:
            pattern = re.compile(
                r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
                re.IGNORECASE,
            )
            for m in pattern.finditer(pr_body):
                closing_issue_num = int(m.group(1))
                # Skip if already matched via branch or title
                if any(i["github_issue_number"] == closing_issue_num for i in matched_issues):
                    continue
                candidate = await db.fetch_one(
                    """SELECT * FROM issues
                       WHERE batch_id = ? AND assigned_to = ? AND github_issue_number = ?
                       LIMIT 1""",
                    (batch_id, student["id"], closing_issue_num),
                )
                if candidate:
                    matched_issues.append(candidate)
                    match_strategies.append(f"pr-body-closes #{closing_issue_num}")

        # Strategy 4: Last-resort — oldest unfinished issue for this student in the batch.
        if not matched_issues:
            issue = await db.fetch_one(
                """SELECT * FROM issues 
                   WHERE batch_id = ? AND assigned_to = ? AND status IN ('assigned', 'open')
                   ORDER BY week_number ASC LIMIT 1""",
                (batch_id, student["id"]),
            )
            if issue:
                matched_issues.append(issue)
                match_strategies.append(f"fallback-oldest-open (issue #{issue['github_issue_number']})")

        if matched_issues:
            strategy_str = ", ".join(match_strategies)
            logger.info(
                f"PR #{pr_number} by {student_github_username} → issues {[i['github_issue_number'] for i in matched_issues]} "
                f"[strategies: {strategy_str}]"
            )
        else:
            logger.warning(
                f"PR #{pr_number} by {student_github_username} in batch {batch_id}: "
                f"no matching issue found — submission not recorded"
            )
        # ─────────────────────────────────────────────────────────────────────

        # Guard: submissions.issue_id is NOT NULL — skip insert if no issue matched.
        # This prevents an IntegrityError when the PR branch name doesn't follow
        # the expected '{issue_number}-description' convention.
        if not matched_issues:
            logger.warning(
                f"PR #{pr_number} by {student_github_username} in batch {batch_id}: "
                f"no matching issue found — submission NOT recorded to avoid NOT NULL violation. "
                f"Admin can manually link this PR via the Sync PRs flow."
            )
            return {"submission_id": None, "issue_id": None, "status": "ignored_no_issue_match"}

        submission_ids = []
        issue_ids = []
        for issue in matched_issues:
            # Record the submission for each issue
            submission_id = await db.insert(
                """INSERT INTO submissions (issue_id, student_id, batch_id, pr_url, pr_number, status)
                   VALUES (?, ?, ?, ?, ?, 'open')""",
                (issue["id"], student["id"], batch_id, pr_url, pr_number),
            )
            submission_ids.append(submission_id)
            issue_ids.append(issue["id"])

            # Update issue status
            await db.execute(
                "UPDATE issues SET status = 'in_progress' WHERE id = ?", (issue["id"],)
            )

        logger.info(f"Recorded {len(submission_ids)} submissions for PR #{pr_number} by {student_github_username} in batch {batch_id}")
        # Return first submission for backwards compatibility with legacy callers
        return {"submission_id": submission_ids[0], "issue_id": issue_ids[0]}

    async def update_submission_status(
        self, batch_id: int, pr_number: int, status: str
    ) -> bool:
        """
        Update the status of a PR submission.
        Called by webhook when check_suite completes or PR is merged.
        If a PR matches multiple submissions (closed multiple issues), updates all.
        """
        submissions = await db.fetch_all(
            "SELECT * FROM submissions WHERE batch_id = ? AND pr_number = ?",
            (batch_id, pr_number),
        )
        if not submissions:
            return False

        now = datetime.utcnow().isoformat()
        
        for submission in submissions:
            # Idempotency guard: if submission is already in the target status, skip
            if submission["status"] == status:
                continue

            if status == "merged":
                await db.execute(
                    "UPDATE submissions SET status = 'merged', merged_at = ? WHERE id = ?",
                    (now, submission["id"]),
                )
                
                if submission["issue_id"]:
                    issue_row = await db.fetch_one(
                        "SELECT week_number, status FROM issues WHERE id = ?",
                        (submission["issue_id"],),
                    )
                    issue_already_completed = (
                        issue_row and issue_row["status"] == "completed"
                    )

                    # Always mark the issue completed
                    await db.execute(
                        "UPDATE issues SET status = 'completed' WHERE id = ?",
                        (submission["issue_id"],),
                    )

                    # Only update progress if this is the FIRST time this issue is completed
                    if not issue_already_completed and issue_row:
                        week = issue_row["week_number"]
                        student_id = submission["student_id"]
                        existing_progress = await db.fetch_one(
                            "SELECT id FROM progress WHERE student_id = ? AND batch_id = ? AND week = ?",
                            (student_id, batch_id, week),
                        )
                        if existing_progress:
                            await db.execute(
                                """UPDATE progress 
                                   SET issues_completed = issues_completed + 1, 
                                       prs_merged = prs_merged + 1,
                                       score = score + 25,
                                       updated_at = CURRENT_TIMESTAMP
                                   WHERE student_id = ? AND batch_id = ? AND week = ?""",
                                (student_id, batch_id, week),
                            )
                            logger.info(
                                f"Updated progress for student {student_id}, batch {batch_id}, week {week}: +25 score"
                            )
                        else:
                            await db.insert(
                                """INSERT INTO progress
                                   (student_id, batch_id, week, issues_assigned, issues_completed, prs_merged, score)
                                   VALUES (?, ?, ?, 1, 1, 1, 25)""",
                                (student_id, batch_id, week),
                            )
                            logger.info(
                                f"Created progress row for student {student_id}, batch {batch_id}, week {week} "
                                f"(was missing — seeded with completed=1, score=25)"
                            )
                    elif issue_already_completed:
                        logger.info(
                            f"Issue {submission['issue_id']} already completed — skipping progress increment "
                            f"(duplicate PR #{pr_number} for student {submission['student_id']})"
                        )
            else:
                await db.execute(
                    "UPDATE submissions SET status = ?, reviewed_at = ? WHERE id = ?",
                    (status, now, submission["id"]),
                )

        return True

    async def get_batch_progress(self, batch_id: int) -> list[dict]:
        """Get aggregated progress for all students in a batch."""
        return await db.fetch_all(
            """SELECT 
                 s.id as student_id,
                 s.first_name,
                 s.last_name,
                 s.github_username,
                 e.status as enrollment_status,
                 COALESCE(SUM(p.issues_assigned), 0) as total_assigned,
                 COALESCE(SUM(p.issues_completed), 0) as total_completed,
                 COALESCE(SUM(p.prs_merged), 0) as total_prs_merged,
                 COALESCE(SUM(p.score), 0) as total_score
               FROM enrollments e
               JOIN students s ON e.student_id = s.id
               LEFT JOIN progress p ON p.student_id = s.id AND p.batch_id = e.batch_id
               WHERE e.batch_id = ?
               GROUP BY s.id
               ORDER BY total_score DESC""",
            (batch_id,),
        )

    async def get_student_progress(self, student_id: int) -> list[dict]:
        """Get all progress records for a student across all batches."""
        return await db.fetch_all(
            """SELECT 
                 p.*, b.domain, b.batch_number, b.repo_name
               FROM progress p
               JOIN batches b ON p.batch_id = b.id
               WHERE p.student_id = ?
               ORDER BY b.domain, p.week""",
            (student_id,),
        )


# Global service instance
batch_service = BatchService()
