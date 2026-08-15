"""
scheduler.py

Phase 5, Step 5.1: a REAL scheduler that runs the automatic pipeline
(Data Agent -> Knowledge Agent -> Decision Agent) on its own, on a
recurring schedule, instead of only ever running when someone manually
calls POST /recommendations/run-now.

Uses APScheduler's BackgroundScheduler, which runs jobs on their own
thread inside the same process as the FastAPI app -- no separate
worker process, message queue, or extra infrastructure needed.

IMPORTANT: this does NOT reimplement the pipeline logic. It calls the
exact same function the /run-now endpoint calls
(run_auto_pipeline_now), just on a timer instead of a manual HTTP
request. That's intentional -- see Step 5.3 in the plan: /run-now stays
exactly as it is (manual trigger / testing endpoint), and this module
is simply what calls it automatically for production use. One
orchestration function, two ways to trigger it.
"""

import logging
from datetime import datetime, timedelta, UTC

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.routers.recommendations import run_auto_pipeline_now

logger = logging.getLogger("insightos.scheduler")

# V2, Step 5.1: how often the automatic pipeline runs on its own, in
# hours. Kept as a local constant (not in config.py) to stay within
# this step's file scope -- can be promoted to a setting later if it
# needs to be tuned per environment.
SCHEDULER_INTERVAL_HOURS = 1

_scheduler: BackgroundScheduler | None = None


def run_scheduled_pipeline():
    """
    The actual job that runs on a schedule.

    run_auto_pipeline_now() normally gets its db session from FastAPI's
    `Depends(get_db)`, which only exists during an HTTP request. There
    is no HTTP request here -- the scheduler calls this on its own, in
    the background -- so this function opens its own session directly
    from SessionLocal, and always closes it afterward, success or
    failure.
    """
    db = SessionLocal()
    try:
        result = run_auto_pipeline_now(db=db)
        logger.info("Scheduled pipeline run finished: %s", result)
    except Exception:
        # A single bad run (bad data, a flaky LLM call, whatever)
        # should never crash the scheduler or take the whole app down
        # with it -- log it and let the next scheduled run try again.
        logger.exception("Scheduled pipeline run failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """
    Creates and starts the background scheduler, running
    run_scheduled_pipeline() every SCHEDULER_INTERVAL_HOURS.

    Safe to call more than once (e.g. if app startup logic runs twice
    in some environments) -- returns the existing scheduler instead of
    starting a second, duplicate one.

    Not wired into app startup yet -- that's Step 5.2 (main.py).
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler already running, reusing existing instance")
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_scheduled_pipeline,
        trigger="interval",
        hours=SCHEDULER_INTERVAL_HOURS,
        id="auto_pipeline_job",
        replace_existing=True,
        # By default, APScheduler's interval trigger waits a FULL
        # interval before its first run (so "every hour" would sit idle
        # for a whole hour after startup before checking anything even
        # once). Explicitly setting next_run_time to a few seconds from
        # now gives us one run shortly after startup, then every
        # SCHEDULER_INTERVAL_HOURS after that.
        #
        # NOTE: next_run_time=None is NOT "use the default" -- it
        # actually PAUSES the job so it never fires on its own. Tested
        # this directly; worth calling out since it's an easy mistake.
        next_run_time=datetime.now(UTC) + timedelta(seconds=10),
    )
    _scheduler.start()
    logger.info(
        "Scheduler started: automatic pipeline will run every %s hour(s)",
        SCHEDULER_INTERVAL_HOURS,
    )
    return _scheduler


def stop_scheduler():
    """
    Shuts the scheduler down cleanly. Meant to be called on app
    shutdown, so background jobs don't keep running (or half-run)
    after the app itself has stopped.
    """
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")