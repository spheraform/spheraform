"""Celery application for distributed task processing."""

from celery import Celery
from spheraform_core.config import settings

celery_app = Celery(
    "spheraform",
    broker=settings.redis_url,
    backend=settings.redis_url,  # Store task results in Redis
    include=[
        "spheraform_api.tasks.download",
        "spheraform_api.tasks.crawl",
        "spheraform_api.tasks.export",
    ]
)

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit
    worker_prefetch_multiplier=1,  # Reduced from 4: only 1 task per worker to prevent memory issues
    worker_max_tasks_per_child=50,  # Reduced from 1000: restart after 50 tasks to prevent memory leaks
    task_acks_late=True,  # Ack after completion (for retry on crash)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    result_expires=3600,  # Keep results 1 hour
    broker_connection_retry_on_startup=True,
)

# Task routing (separate queues by workload)
# Match the explicit task names defined in tasks/*.py (e.g., name="download.process_job")
celery_app.conf.task_routes = {
    "download.*": {"queue": "downloads"},
    "crawl.*": {"queue": "crawls"},
    "export.*": {"queue": "exports"},
}
