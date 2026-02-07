"""
Celery configuration for background tasks.
"""

import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('smart_work_sequencer')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Celery Beat schedule for automated weekly reports
app.conf.beat_schedule = {
    'generate-weekly-reports': {
        'task': 'reports.tasks.generate_all_weekly_reports',
        # Run every Monday at 9 AM UTC
        'schedule': crontab(hour=9, minute=0, day_of_week=1),
    },
    'refresh-jira-tokens': {
        'task': 'authentication.tasks.refresh_expiring_tokens',
        # Run every 6 hours
        'schedule': crontab(hour='*/6', minute=0),
    },
}

app.conf.timezone = 'UTC'
