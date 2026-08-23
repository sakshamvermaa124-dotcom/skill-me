"""
SkillMe — Scheduler Service
Wraps APScheduler for lifecycle management inside FastAPI.
Task content is generated dynamically per student (see routes/tasks.py),
so there is no weekly auto-assignment job to run here anymore — this just
hosts the scheduler instance that other services (e.g. monitoring) register
jobs onto.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("skillme.scheduler")


class SchedulerService:
    """Wraps APScheduler for lifecycle management inside FastAPI."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    def start(self):
        self._scheduler.start()
        logger.info("Scheduler started.")

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down.")


# Global instance
scheduler_service = SchedulerService()
