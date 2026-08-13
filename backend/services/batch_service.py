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

        # Automatically assign tasks if the batch has assigned weeks, or default to Week 1 if active
        import json
        try:
            weeks_to_assign = json.loads(batch.get("weeks_assigned") or "[]")
            if not weeks_to_assign and batch.get("status") == "active":
                weeks_to_assign = [1]
            for w in weeks_to_assign:
                logger.info(f"Auto-assigning Week {w} tasks for newly enrolled student {student_id}")
                await self.assign_week_from_task_repo(batch_id=batch_id, week_number=w)
        except Exception as e:
            logger.warning(f"Could not auto-assign tasks on enrollment for student {student_id}: {e}")

        return {
            "enrollment_id": enrollment_id,
            "student_id": student_id,
            "batch_id": batch_id,
            "github_invite_status": invite_status,
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

        # Strategy 1: Branch prefix matches github_issue_number exactly.
        # Covers the happy path: student used GitHub's "Create a branch" button,
        # which names the branch '{github_issue_number}-{slug}'.
        if pr_head_branch and not issue:
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
                    match_strategy = f"branch-prefix #{linked_issue_number}"

        # Strategy 2: PR title keyword match against issue titles.
        # Handles cases like branch='4-week-1-build-navigation-bar' where the
        # prefix '4' is a local counter, not the GitHub issue number.
        # We tokenize both the PR title and each open issue title and find the
        # one with the most word overlap (minimum 2 words must match).
        if not issue and pr_head_branch:
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
                issue = best_issue
                match_strategy = f"title-keyword-match (score={best_score}, issue #{issue['github_issue_number']})"

        # Strategy 3: PR body closing keyword — looks for "Fixes #N", "Closes #N",
        # "Resolves #N" in the PR description, which GitHub itself uses to auto-close issues.
        if not issue and pr_body:
            pattern = re.compile(
                r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
                re.IGNORECASE,
            )
            for m in pattern.finditer(pr_body):
                closing_issue_num = int(m.group(1))
                candidate = await db.fetch_one(
                    """SELECT * FROM issues
                       WHERE batch_id = ? AND assigned_to = ? AND github_issue_number = ?
                       LIMIT 1""",
                    (batch_id, student["id"], closing_issue_num),
                )
                if candidate:
                    issue = candidate
                    match_strategy = f"pr-body-closes #{closing_issue_num}"
                    break

        # Strategy 4: Last-resort — oldest unfinished issue for this student in the batch.
        # This guarantees we never store a NULL issue_id for an enrolled student.
        # It may be wrong, but it's better than losing the submission entirely;
        # admins can correct it via the Sync PRs flow if needed.
        if not issue:
            issue = await db.fetch_one(
                """SELECT * FROM issues 
                   WHERE batch_id = ? AND assigned_to = ? AND status IN ('assigned', 'open')
                   ORDER BY week_number ASC LIMIT 1""",
                (batch_id, student["id"]),
            )
            if issue:
                match_strategy = f"fallback-oldest-open (issue #{issue['github_issue_number']})"

        if issue:
            logger.info(
                f"PR #{pr_number} by {student_github_username} → issue #{issue['github_issue_number']} "
                f"[strategy: {match_strategy}]"
            )
        else:
            logger.warning(
                f"PR #{pr_number} by {student_github_username} in batch {batch_id}: "
                f"no matching issue found — submission recorded without issue_id"
            )
        # ─────────────────────────────────────────────────────────────────────

        issue_id = issue["id"] if issue else None

        # Guard: submissions.issue_id is NOT NULL — skip insert if no issue matched.
        # This prevents an IntegrityError when the PR branch name doesn't follow
        # the expected '{issue_number}-description' convention.
        if issue_id is None:
            logger.warning(
                f"PR #{pr_number} by {student_github_username} in batch {batch_id}: "
                f"no matching issue found — submission NOT recorded to avoid NOT NULL violation. "
                f"Admin can manually link this PR via the Sync PRs flow."
            )
            return {"submission_id": None, "issue_id": None, "status": "ignored_no_issue_match"}

        # Record the submission
        submission_id = await db.insert(
            """INSERT INTO submissions (issue_id, student_id, batch_id, pr_url, pr_number, status)
               VALUES (?, ?, ?, ?, ?, 'open')""",
            (issue_id, student["id"], batch_id, pr_url, pr_number),
        )

        # Update issue status
        if issue:
            await db.execute(
                "UPDATE issues SET status = 'in_progress' WHERE id = ?", (issue["id"],)
            )

        logger.info(f"Recorded submission: PR #{pr_number} by {student_github_username} in batch {batch_id}")
        return {"submission_id": submission_id, "issue_id": issue_id}

    async def update_submission_status(
        self, batch_id: int, pr_number: int, status: str
    ) -> bool:
        """
        Update the status of a PR submission.
        Called by webhook when check_suite completes or PR is merged.
        """
        submission = await db.fetch_one(
            "SELECT * FROM submissions WHERE batch_id = ? AND pr_number = ?",
            (batch_id, pr_number),
        )
        if not submission:
            return False

        now = datetime.utcnow().isoformat()

        # Idempotency guard: if submission is already in the target status, skip
        # This prevents score inflation from duplicate webhook deliveries
        if submission["status"] == status:
            return True

        if status == "merged":
            await db.execute(
                "UPDATE submissions SET status = 'merged', merged_at = ? WHERE id = ?",
                (now, submission["id"]),
            )
            # Mark issue as completed — but only increment progress if it wasn't
            # already completed. This prevents duplicate PRs for the same issue
            # (e.g. a student opens multiple PRs) from inflating the score.
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
