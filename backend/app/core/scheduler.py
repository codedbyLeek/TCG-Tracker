"""Application-wide scheduler: one shared APScheduler instance and job registry."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.sync.one_piece import sync_all_sets
from app.sync.pokemon import sync_all_expansions, sync_recent_expansions

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="America/New_York")


def _run_job(job_name: str, sync_fn) -> None:
    """Run one sync function with its own DB session, logging the outcome."""
    logger.info("Job %s starting", job_name)
    db = SessionLocal()
    try:
        summary = sync_fn(db)
    except Exception:
        logger.exception("Job %s crashed", job_name)
        return
    finally:
        db.close()

    logger.info(
        "Job %s finished: %d attempted, %d failed, %d created, %d updated",
        job_name,
        summary["sets_attempted"],
        summary["sets_failed"],
        summary["created"],
        summary["updated"],
    )
    for failed_id, error in summary["failures"]:
        logger.error("Job %s - %s failed: %s", job_name, failed_id, error)


def one_piece_nightly() -> None:
    _run_job("one_piece_nightly", sync_all_sets)


def pokemon_recent() -> None:
    _run_job("pokemon_recent", sync_recent_expansions)


def pokemon_full_sweep() -> None:
    _run_job("pokemon_full_sweep", sync_all_expansions)


def register_jobs() -> None:
    """Attach all recurring jobs to the scheduler. Called once at app startup."""
    scheduler.add_job(
        one_piece_nightly,
        trigger=CronTrigger(hour=3, minute=0),
        id="one_piece_nightly",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        pokemon_recent,
        trigger=CronTrigger(day="*/2", hour=3, minute=30),
        id="pokemon_recent",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        pokemon_full_sweep,
        trigger=CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="pokemon_full_sweep",
        replace_existing=True,
        max_instances=1,
    )