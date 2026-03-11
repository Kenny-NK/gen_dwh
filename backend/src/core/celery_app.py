"""Celery app configuration (T032)."""

from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "gendwh",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.services.scheduler",
        "src.tasks.cleanup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "dispatch-due-schedules": {
            "task": "src.services.scheduler.dispatch_due_schedules",
            "schedule": 60.0,
        },
        "cleanup-expired-previews": {
            "task": "src.tasks.cleanup.cleanup_expired_previews",
            "schedule": 300.0,
        },
        "process-cleanup-jobs": {
            "task": "src.tasks.cleanup.process_cleanup_jobs",
            "schedule": 60.0,
        },
    },
)
