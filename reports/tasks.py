"""
Celery tasks for report generation.
"""

import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def generate_weekly_report_for_user(user_id: str):
    """Generate weekly report for a specific user."""
    from core.models import User
    from reports.services import ReportService
    
    try:
        user = User.objects.get(id=user_id)
        
        # Calculate last week's date range
        today = timezone.now().date()
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = start_of_last_week + timedelta(days=6)
        
        since = timezone.make_aware(datetime.combine(start_of_last_week, datetime.min.time()))
        until = timezone.make_aware(datetime.combine(end_of_last_week, datetime.max.time()))
        
        service = ReportService(user)
        report = service.create_weekly_report(since, until)
        
        logger.info(f"Generated weekly report for {user.email}: {report.id}")
        return str(report.id)
    
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return None
    except Exception as e:
        logger.exception(f"Error generating weekly report for user {user_id}: {e}")
        raise


@shared_task
def generate_all_weekly_reports():
    """Generate weekly reports for all active users."""
    from core.models import User
    
    # Get users with at least one integration connected
    active_users = User.objects.filter(
        is_active=True
    ).filter(
        github_connected=True
    ) | User.objects.filter(
        is_active=True
    ).filter(
        jira_connected=True
    )
    
    active_users = active_users.distinct()
    
    logger.info(f"Generating weekly reports for {active_users.count()} users")
    
    for user in active_users:
        generate_weekly_report_for_user.delay(str(user.id))
    
    return f"Queued reports for {active_users.count()} users"


@shared_task
def sync_user_data(user_id: str, days: int = 7):
    """Sync GitHub and Jira data for a user."""
    from core.models import User
    from reports.services import ReportService
    
    try:
        user = User.objects.get(id=user_id)
        
        until = timezone.now()
        since = until - timedelta(days=days)
        
        service = ReportService(user)
        results = service.sync_data_for_range(since, until)
        
        logger.info(f"Synced data for {user.email}: {results}")
        return results
    
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return None
    except Exception as e:
        logger.exception(f"Error syncing data for user {user_id}: {e}")
        raise
