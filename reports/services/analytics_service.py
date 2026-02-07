"""
Analytics service for effort vs output analysis and hygiene detection.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from django.db.models import Count, Sum, Q
from django.utils import timezone

from core.models import (
    User, Commit, Ticket, TicketActivity, 
    Worklog, HygieneAlert
)
from .ai_service import AIService

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for analyzing work patterns and detecting issues."""
    
    def __init__(self, user: User):
        self.user = user
        self.ai_service = AIService()
    
    def analyze_ticket_effort(
        self,
        ticket: Ticket,
        since: datetime,
        until: datetime,
    ) -> Dict[str, Any]:
        """Analyze effort vs output for a single ticket."""
        # Get commits for this ticket
        commits = Commit.objects.filter(
            user=self.user,
            ticket=ticket,
            committed_at__gte=since,
            committed_at__lte=until,
        )
        
        # Get status changes
        status_changes = TicketActivity.objects.filter(
            user=self.user,
            ticket=ticket,
            activity_type='status_change',
            activity_at__gte=since,
            activity_at__lte=until,
        )
        
        # Get worklogs
        worklogs = Worklog.objects.filter(
            user=self.user,
            ticket=ticket,
            started_at__gte=since,
            started_at__lte=until,
        )
        
        total_time_seconds = worklogs.aggregate(
            total=Sum('time_spent_seconds')
        )['total'] or 0
        
        ticket_data = {
            'key': ticket.key,
            'title': ticket.title,
            'status': ticket.status,
            'commits_count': commits.count(),
            'status_changes_count': status_changes.count(),
            'time_logged_seconds': total_time_seconds,
            'time_logged_display': self._format_time(total_time_seconds),
        }
        
        # Get AI analysis
        analysis = self.ai_service.generate_effort_analysis(ticket_data)
        
        return {
            **ticket_data,
            'analysis': analysis,
        }
    
    def _format_time(self, seconds: int) -> str:
        """Format seconds into human-readable string."""
        if seconds == 0:
            return '0h'
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}m"
    
    def detect_hygiene_issues(
        self,
        since: datetime,
        until: datetime,
    ) -> List[HygieneAlert]:
        """
        Detect and create hygiene alerts for the date range.
        
        Checks for:
        1. Commits without Jira tickets
        2. Status changes without commits
        3. Time logged without code
        4. Tickets worked on but never moved
        """
        alerts = []
        
        # 1. Commits without Jira tickets
        unlinked_commits = Commit.objects.filter(
            user=self.user,
            is_unlinked=True,
            committed_at__gte=since,
            committed_at__lte=until,
        )
        
        for commit in unlinked_commits:
            alert, created = HygieneAlert.objects.get_or_create(
                user=self.user,
                alert_type='commit_no_ticket',
                commit=commit,
                detected_for_start=since.date(),
                detected_for_end=until.date(),
                defaults={
                    'severity': 'warning',
                    'title': f"Commit without ticket reference",
                    'description': f"Commit {commit.sha[:7]} in {commit.repository.full_name} has no Jira ticket reference.",
                    'recommendation': "Add a ticket reference (e.g., PROJ-123) to your commit messages for better tracking.",
                }
            )
            if created:
                alerts.append(alert)
        
        # 2. Status changes without commits (non-code activity)
        tickets_with_status_changes = TicketActivity.objects.filter(
            user=self.user,
            activity_type='status_change',
            activity_at__gte=since,
            activity_at__lte=until,
        ).values_list('ticket_id', flat=True).distinct()
        
        for ticket_id in tickets_with_status_changes:
            ticket = Ticket.objects.get(id=ticket_id)
            
            # Check if there are any commits for this ticket
            commits_count = Commit.objects.filter(
                user=self.user,
                ticket=ticket,
                committed_at__gte=since,
                committed_at__lte=until,
            ).count()
            
            if commits_count == 0:
                alert, created = HygieneAlert.objects.get_or_create(
                    user=self.user,
                    alert_type='status_no_commit',
                    ticket=ticket,
                    detected_for_start=since.date(),
                    detected_for_end=until.date(),
                    defaults={
                        'severity': 'info',
                        'title': f"Status change without commits",
                        'description': f"Ticket {ticket.key} had status changes but no associated commits.",
                        'recommendation': "This may indicate non-code work like design or documentation. Consider logging this as part of your workflow.",
                    }
                )
                if created:
                    alerts.append(alert)
        
        # 3. Time logged without code
        tickets_with_worklogs = Worklog.objects.filter(
            user=self.user,
            started_at__gte=since,
            started_at__lte=until,
        ).values_list('ticket_id', flat=True).distinct()
        
        for ticket_id in tickets_with_worklogs:
            ticket = Ticket.objects.get(id=ticket_id)
            
            commits_count = Commit.objects.filter(
                user=self.user,
                ticket=ticket,
                committed_at__gte=since,
                committed_at__lte=until,
            ).count()
            
            if commits_count == 0:
                # Check if we already have an alert
                existing = HygieneAlert.objects.filter(
                    user=self.user,
                    alert_type='time_no_code',
                    ticket=ticket,
                    detected_for_start=since.date(),
                    detected_for_end=until.date(),
                ).exists()
                
                if not existing:
                    alert = HygieneAlert.objects.create(
                        user=self.user,
                        alert_type='time_no_code',
                        ticket=ticket,
                        detected_for_start=since.date(),
                        detected_for_end=until.date(),
                        severity='info',
                        title=f"Time logged without code",
                        description=f"Time was logged on {ticket.key} but no commits were made.",
                        recommendation="If this was non-coding work, this is fine. Otherwise, ensure commits reference the ticket.",
                    )
                    alerts.append(alert)
        
        # 4. Tickets worked on but never moved (stalled)
        # Get tickets with commits but no status changes
        tickets_with_commits = Commit.objects.filter(
            user=self.user,
            committed_at__gte=since,
            committed_at__lte=until,
            ticket__isnull=False,
        ).values_list('ticket_id', flat=True).distinct()
        
        for ticket_id in tickets_with_commits:
            ticket = Ticket.objects.get(id=ticket_id)
            
            status_changes = TicketActivity.objects.filter(
                user=self.user,
                ticket=ticket,
                activity_type='status_change',
                activity_at__gte=since,
                activity_at__lte=until,
            ).count()
            
            if status_changes == 0:
                alert, created = HygieneAlert.objects.get_or_create(
                    user=self.user,
                    alert_type='stalled_ticket',
                    ticket=ticket,
                    detected_for_start=since.date(),
                    detected_for_end=until.date(),
                    defaults={
                        'severity': 'warning',
                        'title': f"Stalled ticket",
                        'description': f"Ticket {ticket.key} has commits but no status changes.",
                        'recommendation': "Consider updating the ticket status to reflect your progress.",
                    }
                )
                if created:
                    alerts.append(alert)
        
        return alerts
    
    def get_effort_analysis_summary(
        self,
        since: datetime,
        until: datetime,
    ) -> Dict[str, Any]:
        """Get effort vs output analysis for all tickets in date range."""
        # Get all tickets with activity
        ticket_ids = set()
        
        # From commits
        ticket_ids.update(
            Commit.objects.filter(
                user=self.user,
                committed_at__gte=since,
                committed_at__lte=until,
                ticket__isnull=False,
            ).values_list('ticket_id', flat=True)
        )
        
        # From activities
        ticket_ids.update(
            TicketActivity.objects.filter(
                user=self.user,
                activity_at__gte=since,
                activity_at__lte=until,
            ).values_list('ticket_id', flat=True)
        )
        
        # From worklogs
        ticket_ids.update(
            Worklog.objects.filter(
                user=self.user,
                started_at__gte=since,
                started_at__lte=until,
            ).values_list('ticket_id', flat=True)
        )
        
        analyses = {
            'fast_wins': [],
            'high_effort_low_output': [],
            'stalled': [],
            'normal': [],
        }
        
        for ticket_id in ticket_ids:
            ticket = Ticket.objects.get(id=ticket_id)
            analysis = self.analyze_ticket_effort(ticket, since, until)
            classification = analysis['analysis']['classification']
            analyses[classification].append(analysis)
        
        return {
            'summary': {
                'fast_wins_count': len(analyses['fast_wins']),
                'high_effort_low_output_count': len(analyses['high_effort_low_output']),
                'stalled_count': len(analyses['stalled']),
                'normal_count': len(analyses['normal']),
            },
            'details': analyses,
        }
    
    def get_hygiene_summary(
        self,
        since: datetime,
        until: datetime,
    ) -> Dict[str, Any]:
        """Get hygiene alerts summary for a date range."""
        alerts = HygieneAlert.objects.filter(
            user=self.user,
            detected_for_start__gte=since.date(),
            detected_for_end__lte=until.date(),
            is_resolved=False,
        )
        
        by_type = alerts.values('alert_type').annotate(count=Count('id'))
        
        return {
            'total_alerts': alerts.count(),
            'by_type': {item['alert_type']: item['count'] for item in by_type},
            'alerts': [
                {
                    'id': str(a.id),
                    'type': a.alert_type,
                    'severity': a.severity,
                    'title': a.title,
                    'description': a.description,
                    'recommendation': a.recommendation,
                    'ticket_key': a.ticket.key if a.ticket else None,
                    'commit_sha': a.commit.sha[:7] if a.commit else None,
                }
                for a in alerts[:20]  # Limit to 20 most recent
            ]
        }
