from celery import Celery

from app.config import settings

celery_app = Celery("carbon", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
