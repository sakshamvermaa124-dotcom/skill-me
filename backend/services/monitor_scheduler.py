"""
SkillMe — Monitor Scheduler
Integrates monitoring jobs into the existing APScheduler.

Schedule:
  - Every 5 min:   Health probes
  - Every 15 min:  Critical-path smoke tests
  - Every 30 min:  DB integrity + stuck-student detection
  - Every 2 hours: Full E2E lifecycle tests
"""

import logging
from apscheduler.triggers.interval import IntervalTrigger
from services.monitor_service import (
    run_all_probes, run_smoke_tests, run_full_e2e_tests,
    check_db_integrity, detect_stuck_students,
)

logger = logging.getLogger("skillme.monitor.scheduler")


def register_monitor_jobs(scheduler) -> None:
    """Register all monitoring jobs on the existing APScheduler instance."""

    # Health probes — every 5 minutes
    scheduler.add_job(
        run_all_probes,
        trigger=IntervalTrigger(minutes=5),
        id="monitor_health_probes",
        replace_existing=True,
        misfire_grace_time=120,
    )
    logger.info("Registered: health probes (every 5 min)")

    # Smoke tests — every 15 minutes
    scheduler.add_job(
        run_smoke_tests,
        trigger=IntervalTrigger(minutes=15),
        id="monitor_smoke_tests",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("Registered: smoke tests (every 15 min)")

    # DB integrity + stuck students — every 30 minutes
    async def integrity_and_stuck():
        await check_db_integrity()
        await detect_stuck_students()

    scheduler.add_job(
        integrity_and_stuck,
        trigger=IntervalTrigger(minutes=30),
        id="monitor_db_integrity",
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info("Registered: DB integrity + stuck detection (every 30 min)")

    # Full E2E tests — every 2 hours
    scheduler.add_job(
        run_full_e2e_tests,
        trigger=IntervalTrigger(hours=2),
        id="monitor_full_e2e",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered: full E2E tests (every 2 hours)")

    logger.info("All monitoring jobs registered.")
