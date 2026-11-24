"""
SkillMe - Admin CLI
Command-line tool for quick admin operations.

Usage:
    python cli.py enroll-student --email john@example.com
    python cli.py list-students
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
    """SkillMe Admin CLI - Manage students and submissions."""
    pass


# ==============================================
# Students
# ==============================================

@cli.command("enroll-student")
@click.option("--email", "-e", required=True, help="Student email")
def enroll_student(email):
    """Enroll a student (they must have already applied). Does not send the offer letter."""
    async def _run():
        await _init()
        from db.database import db
        from services.enrollment_service import enrollment_service

        student = await db.fetch_one(
            "SELECT * FROM students WHERE lower(email) = lower(?)", (email.strip(),)
        )
        if not student:
            console.print(f"[red]No student found with email: {email}[/red]")
            console.print("They need to apply first at /apply")
            return

        try:
            with console.status(f"Enrolling {student['first_name']}..."):
                await enrollment_service.enroll_student(student["id"])

            console.print(f"[OK] Enrolled {student['first_name']} {student['last_name']}")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

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
        table.add_column("College")
        table.add_column("Status", justify="center")
        table.add_column("Applied", justify="center")

        for s in students:
            status_color = {"applied": "yellow", "shortlisted": "blue", "enrolled": "green", "completed": "cyan", "dropped": "red"}.get(s["status"], "white")
            table.add_row(
                str(s["id"]),
                f"{s['first_name']} {s['last_name']}",
                s["email"],
                s["college"] or "-",
                f"[{status_color}]{s['status']}[/{status_color}]",
                s["created_at"][:10] if s["created_at"] else "-",
            )

        console.print(table)

    run_async(_run())


# ==============================================
# Submissions
# ==============================================

@cli.command("list-pending-submissions")
def list_pending_submissions():
    """List all pending LinkedIn task submissions awaiting review."""
    async def _run():
        await _init()
        from services.submission_service import submission_service

        submissions = await submission_service.list_submissions(status="pending")
        if not submissions:
            console.print("[yellow]No pending submissions.[/yellow]")
            return

        table = Table(title="Pending Submissions", box=box.ROUNDED, show_lines=True)
        table.add_column("ID", style="cyan", justify="center")
        table.add_column("Student", style="bold")
        table.add_column("Week", justify="center")
        table.add_column("LinkedIn URL")
        table.add_column("Submitted", justify="center")

        for s in submissions:
            table.add_row(
                str(s["id"]),
                f"{s['first_name']} {s['last_name']}",
                str(s["week"]),
                s["linkedin_url"],
                s["submitted_at"] or "-",
            )

        console.print(table)

    run_async(_run())


# ==============================================
# Credentials: funnel and follow-up reminders
# ==============================================

@cli.command("credential-funnel")
@click.option("--days", "-d", type=int, default=None, help="Only students unlocked in the last N days")
def credential_funnel(days):
    """Where eligible students drop off: offer seen -> checkout -> pay -> paid -> stipend seat."""
    async def _run():
        await _init()
        from services.credential_reminder_service import funnel_report

        rep = await funnel_report(days)
        title = f"Credential funnel (last {days} days)" if days else "Credential funnel (all time)"
        table = Table(title=title, box=box.ROUNDED)
        table.add_column("Step", style="bold")
        table.add_column("Students", justify="right", style="cyan")
        table.add_column("% of unlocked", justify="right")
        table.add_column("% of previous", justify="right")
        for s in rep["steps"]:
            table.add_row(s["step"], str(s["count"]), f"{s['pct_of_unlocked']}%", f"{s['pct_of_previous']}%")
        console.print(table)
        r = rep["reminders"]
        console.print(
            f"Reminders: {r['credentials_waiting']['emails']} 'credentials waiting' emails "
            f"to {r['credentials_waiting']['people']} people, {r['came_back_from_credentials_email']} came back"
        )
        since = rep["tracking_since"] or "not yet (no browser events recorded)"
        console.print(f"[dim]Browser steps tracked since: {since}. {rep['note']}[/dim]")

    run_async(_run())


@cli.command("credential-reminders")
@click.option("--dry-run/--send", default=True, help="List who is due (default) or actually send")
def credential_reminders(dry_run):
    """Who gets a 'credentials waiting' email today (the daily job sends them)."""
    async def _run():
        await _init()
        from services.credential_reminder_service import get_candidates, send_credential_reminders

        if not dry_run:
            console.print(await send_credential_reminders())
            return
        due = await get_candidates()
        if not due:
            console.print("[yellow]Nobody is due a credential reminder today.[/yellow]")
            return
        table = Table(title="Due today (dry run, nothing sent)", box=box.ROUNDED)
        table.add_column("Email")
        table.add_column("Reminder")
        table.add_column("#", justify="center")
        for c in due:
            table.add_row(c["email"], c["kind"], str(c["step"]))
        console.print(table)

    run_async(_run())


if __name__ == "__main__":
    cli()
