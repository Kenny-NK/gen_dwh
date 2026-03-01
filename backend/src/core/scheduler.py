"""Celery Beat scheduler configuration (T034)."""

from src.core.celery_app import celery_app

# Default beat schedule - will be extended by schedule_service
celery_app.conf.beat_schedule = {
    "cleanup-expired-previews": {
        "task": "src.tasks.cleanup.cleanup_expired_previews",
        "schedule": 300.0,  # every 5 minutes
    },
}
