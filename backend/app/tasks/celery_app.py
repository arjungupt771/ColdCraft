"""Celery app. Run:
    celery -A app.tasks.celery_app worker --loglevel=info          (use --pool=solo on Windows)
    celery -A app.tasks.celery_app beat   --loglevel=info
Redis is the broker. Without it, the in-process scheduler in main.py still handles follow-up checks."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery("coldcraft", broker=settings.REDIS_URL, backend=settings.REDIS_URL, include=["app.tasks.jobs"])
celery.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC",
    task_acks_late=True, task_time_limit=180, result_expires=3600,
    beat_schedule={
        "check-due-followups": {
            "task": "coldcraft.check_due_followups",
            "schedule": crontab(minute=f"*/{max(settings.FOLLOWUP_CHECK_INTERVAL_MINUTES, 1)}"),
        },
        "check-replies": {"task": "coldcraft.check_replies", "schedule": crontab(minute="*/30")},
    },
)
