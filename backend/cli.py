"""
SkillMe - Admin CLI
Command-line tool for quick admin operations.

Usage:
    python cli.py create-batch --domain web-dev --batch 1
    python cli.py add-student --email john@example.com --batch-id 1
    python cli.py assign-issues --batch-id 1 --week 1
    python cli.py batch-status --batch-id 1
    python cli.py list-students
    python cli.py github-check
"""

import asyncio
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def run_async(coro):
    """Helper to run async functions from sync Click commands."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _init():
    """Initialize database connection."""
    from db.database import db
    await db.connect()
    return db


@click.group()
def cli():
    """SkillMe Admin CLI - Manage batches, students, and GitHub automation."""
    pass


# ==============================================
# GitHub
# ==============================================

@cli.command("github-check")
def github_check():
    """Check GitHub API connection and token validity."""
    async def _run():
        await _init()
        from services.github_service import github_service
        user = await github_service.verify_token()
        if user:
            console.print(Panel(
                f"[green]OK Connected[/green]\n"
                f"Authenticated as: [bold]{user['login']}[/bold]\n"
                f"Org: [bold]{github_service.org}[/bold]",
                title="GitHub Status",
                border_style="green",
            ))
        else:
            console.print("[red]X GitHub token is invalid or not configured[/red]")
        await github_service.close()

    run_async(_run())


# ==============================================
# Batches
# ==============================================

@cli.command("create-batch")
@click.option("--domain", "-d", required=True, help="Domain (e.g., web-dev, python)")
@click.option("--batch", "-b", required=True, type=int, help="Batch number")
@click.option("--template", "-t", default=None, help="Override template repo name")
@click.option("--max-students", default=30, type=int, help="Max students per batch")
@click.option("--webhook-url", default=None, help="Webhook URL for PR events")
def create_batch(domain, batch, template, max_students, webhook_url):
    """Create a new batch - provisions a GitHub repo from template."""
    async def _run():
        await _init()
        from services.batch_service import batch_service
        from services.github_service import github_service

        try:
            with console.status(f"Creating batch {domain} #{batch}..."):
                result = await batch_service.create_batch(
                    domain=domain,
                    batch_number=batch,
                    template_repo=template,
                    max_students=max_students,
                    webhook_url=webhook_url,
                )

            console.print(Panel(
                f"[OK] Batch created successfully!\n\n"
                f"ID: [bold]{result['id']}[/bold]\n"
                f"Domain: [bold]{result['domain']}[/bold]\n"
                f"Batch #: [bold]{result['batch_number']}[/bold]\n"
                f"Repo: [bold]{result['repo_name']}[/bold]\n"
                f"Start: {result['start_date']}\n"
                f"End: {result['end_date']}",
                title="New Batch",
                border_style="green",
            ))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await github_service.close()

    run_async(_run())


@cli.command("list-batches")
@click.option("--status", "-s", default=None, help="Filter by status")
def list_batches(status):
    """List all batches."""
    async def _run():
        await _init()
        from services.batch_service import batch_service

        batches = await batch_service.list_batches(status=status)

        if not batches:
            console.print("[yellow]No batches found.[/yellow]")
            return

        table = Table(title="Batches", box=box.ROUNDED, show_lines=True)
        table.add_column("ID", style="cyan", justify="center")
        table.add_column("Domain", style="bold")
        table.add_column("Batch #", justify="center")
        table.add_column("Repo", style="dim")
        table.add_column("Status", justify="center")
        table.add_column("Start", justify="center")
        table.add_column("End", justify="center")

        status_colors = {
            "active": "green",
            "provisioning": "yellow",
            "completed": "blue",
            "archived": "dim",
        }

        for b in batches:
            color = status_colors.get(b["status"], "white")
            table.add_row(
                str(b["id"]),
                b["domain"],
                str(b["batch_number"]),
                b["repo_name"] or "-",
                f"[{color}]{b['status']}[/{color}]",
                b["start_date"] or "-",
                b["end_date"] or "-",
            )

        console.print(table)

    run_async(_run())


@cli.command("batch-status")
@click.option("--batch-id", "-b", required=True, type=int, help="Batch ID")
def batch_status(batch_id):
    """Show detailed batch status with student progress."""
    async def _run():
        await _init()
        from services.batch_service import batch_service

        batch = await batch_service.get_batch(batch_id)
        if not batch:
            console.print(f"[red]Batch {batch_id} not found[/red]")
            return

        console.print(Panel(
            f"Domain: [bold]{batch['domain']}[/bold]  |  "
            f"Batch #: [bold]{batch['batch_number']}[/bold]  |  "
            f"Status: [bold]{batch['status']}[/bold]\n"
            f"Repo: [dim]{batch['repo_name']}[/dim]\n"
            f"Period: {batch['start_date']} → {batch['end_date']}",
            title=f"Batch #{batch_id}",
            border_style="blue",
        ))

        progress = await batch_service.get_batch_progress(batch_id)

        if not progress:
            console.print("[yellow]No students enrolled yet.[/yellow]")
            return

        table = Table(title="Student Progress", box=box.ROUNDED)
        table.add_column("Student", style="bold")
        table.add_column("GitHub", style="dim")
        table.add_column("Status")
        table.add_column("Assigned", justify="center")
        table.add_column("Completed", justify="center")
        table.add_column("PRs Merged", justify="center")
        table.add_column("Score", justify="center", style="bold cyan")

        for s in progress:
            table.add_row(
                f"{s['first_name']} {s['last_name']}",
                s["github_username"] or "-",
                s["enrollment_status"],
                str(s["total_assigned"]),
                str(s["total_completed"]),
                str(s["total_prs_merged"]),
                str(s["total_score"]),
            )

        console.print(table)

    run_async(_run())


# ==============================================
# Students
# ==============================================

@cli.command("add-student")
@click.option("--email", "-e", required=True, help="Student email")
@click.option("--batch-id", "-b", required=True, type=int, help="Batch ID to enroll in")
def add_student(email, batch_id):
    """Add a student to a batch (they must have already applied)."""
    async def _run():
        await _init()
        from db.database import db
        from services.batch_service import batch_service
        from services.github_service import github_service

        student = await db.fetch_one(
            "SELECT * FROM students WHERE email = ?", (email,)
        )
        if not student:
            console.print(f"[red]No student found with email: {email}[/red]")
            console.print("They need to apply first at /apply")
            return

        try:
            with console.status(f"Enrolling {student['first_name']}..."):
                result = await batch_service.add_student_to_batch(
                    student_id=student["id"],
                    batch_id=batch_id,
                )

            console.print(
                f"[OK] Enrolled {student['first_name']} {student['last_name']} "
                f"in batch {batch_id}\n"
                f"GitHub invite: {result['github_invite_status']}"
            )
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await github_service.close()

    run_async(_run())


@cli.command("list-students")
@click.option("--status", "-s", default=None, help="Filter by status")
def list_students(status):
    """List all students."""
    async def _run():
        await _init()
        from db.database import db

        if status:
            students = await db.fetch_all(
                "SELECT * FROM students WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            students = await db.fetch_all(
                "SELECT * FROM students ORDER BY created_at DESC"
            )

        if not students:
            console.print("[yellow]No students found.[/yellow]")
            return

        table = Table(title="Students", box=box.ROUNDED, show_lines=True)
        table.add_column("ID", style="cyan", justify="center")
        table.add_column("Name", style="bold")
        table.add_column("Email")
        table.add_column("GitHub", style="dim")
        table.add_column("College")
        table.add_column("Status", justify="center")
        table.add_column("Applied", justify="center")

        for s in students:
            status_color = {"applied": "yellow", "shortlisted": "blue", "enrolled": "green", "completed": "cyan", "dropped": "red"}.get(s["status"], "white")
            table.add_row(
                str(s["id"]),
                f"{s['first_name']} {s['last_name']}",
                s["email"],
                s["github_username"] or "-",
                s["college"] or "-",
                f"[{status_color}]{s['status']}[/{status_color}]",
                s["created_at"][:10] if s["created_at"] else "-",
            )

        console.print(table)

    run_async(_run())


# ==============================================
# Issue Assignment
# ==============================================

@cli.command("assign-issues")
@click.option("--batch-id", "-b", required=True, type=int, help="Batch ID")
@click.option("--week", "-w", required=True, type=int, help="Week number (1-4)")
@click.option("--issues-file", "-f", default=None, help="JSON file with issue definitions")
def assign_issues(batch_id, week, issues_file):
    """Assign issues for a specific week to all enrolled students."""
    async def _run():
        await _init()
        import json
        from services.batch_service import batch_service
        from services.github_service import github_service
        from db.database import db

        # Load issues from file or use defaults
        if issues_file:
            with open(issues_file) as f:
                issues = json.load(f)
                
            try:
                with console.status(f"Assigning {len(issues)} issues for week {week}..."):
                    result = await batch_service.assign_weekly_issues(
                        batch_id=batch_id,
                        week_number=week,
                        issues=issues,
                    )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                return finally_close()
        else:
            try:
                with console.status(f"Fetching and assigning tasks from GitHub repo for week {week}..."):
                    result = await batch_service.assign_week_from_task_repo(
                        batch_id=batch_id,
                        week_number=week,
                    )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                return finally_close()

            console.print(f"[OK] Assigned {len(result)} issues for week {week}")

            table = Table(box=box.SIMPLE)
            table.add_column("Issue #", justify="center")
            table.add_column("Title")
            table.add_column("Assigned To", justify="center")

            for issue in result:
                table.add_row(
                    str(issue.get("github_issue_number", "-")),
                    issue["title"],
                    str(issue.get("assigned_to", "-")),
                )
            console.print(table)

        def finally_close():
            pass

        try:
            pass
        finally:
            await github_service.close()

    run_async(_run())


if __name__ == "__main__":
    cli()
