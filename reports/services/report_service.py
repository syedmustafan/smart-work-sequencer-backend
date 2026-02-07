"""
Report generation service.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.db.models import Sum, Count, Q
from django.utils import timezone

from core.models import (
    User, Commit, Ticket, TicketActivity, 
    Worklog, WeeklyReport, HygieneAlert
)
from integrations.services import GitHubService, JiraService
from .ai_service import AIService
from .analytics_service import AnalyticsService

logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating work reports."""
    
    def __init__(self, user: User):
        self.user = user
        self.ai_service = AIService()
        self.analytics_service = AnalyticsService(user)
    
    def sync_data_for_range(
        self,
        since: datetime,
        until: datetime,
    ) -> Dict[str, Any]:
        """
        Sync all data from GitHub and Jira for the date range.
        """
        results = {
            'github': {'commits': [], 'repos': []},
            'jira': {'tickets': [], 'activities': [], 'worklogs': []},
        }
        
        # Sync GitHub data
        if self.user.github_connected:
            try:
                github_service = GitHubService(self.user)
                commit_results = github_service.sync_all_tracked_repos(since, until)
                results['github']['commits'] = sum(len(c) for c in commit_results.values())
                results['github']['repos'] = list(commit_results.keys())
            except Exception as e:
                logger.error(f"Error syncing GitHub data: {e}")
        
        # Sync Jira data
        if self.user.jira_connected:
            try:
                jira_service = JiraService(self.user)
                jira_results = jira_service.sync_all_for_date_range(since, until)
                results['jira']['tickets'] = len(jira_results['tickets'])
                results['jira']['activities'] = len(jira_results['activities'])
                results['jira']['worklogs'] = len(jira_results['worklogs'])
            except Exception as e:
                logger.error(f"Error syncing Jira data: {e}")
        
        return results
    
    def generate_report(
        self,
        since: datetime,
        until: datetime,
        sync_first: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive work report for the date range.
        """
        # Optionally sync data first
        if sync_first:
            self.sync_data_for_range(since, until)
        
        # Gather statistics
        stats = self._calculate_stats(since, until)
        
        # Get ticket details
        tickets_data = self._get_tickets_data(since, until)
        
        # Get unlinked commits
        unlinked_commits = self._get_unlinked_commits(since, until)
        
        # Detect hygiene issues
        self.analytics_service.detect_hygiene_issues(since, until)
        hygiene_summary = self.analytics_service.get_hygiene_summary(since, until)
        
        # Get effort analysis
        effort_analysis = self.analytics_service.get_effort_analysis_summary(since, until)
        
        # Build report data
        report_data = {
            'date_range': {
                'start': since.strftime('%Y-%m-%d'),
                'end': until.strftime('%Y-%m-%d'),
            },
            'stats': stats,
            'tickets': tickets_data,
            'unlinked_commits': unlinked_commits,
            'hygiene': hygiene_summary,
            'effort_analysis': effort_analysis,
        }
        
        # Generate AI summary
        report_data['summary'] = self.ai_service.generate_work_summary(report_data)
        
        # Generate markdown report
        report_data['markdown'] = self._generate_markdown_report(report_data)
        
        return report_data
    
    def _calculate_stats(
        self,
        since: datetime,
        until: datetime,
    ) -> Dict[str, Any]:
        """Calculate aggregate statistics for the date range."""
        # Total commits
        total_commits = Commit.objects.filter(
            user=self.user,
            committed_at__gte=since,
            committed_at__lte=until,
        ).count()
        
        # Unlinked commits
        unlinked_commits = Commit.objects.filter(
            user=self.user,
            committed_at__gte=since,
            committed_at__lte=until,
            is_unlinked=True,
        ).count()
        
        # Tickets worked on (from commits or activities)
        ticket_ids = set()
        
        # From commits
        commit_ticket_ids = Commit.objects.filter(
            user=self.user,
            committed_at__gte=since,
            committed_at__lte=until,
            ticket__isnull=False,
        ).values_list('ticket_id', flat=True)
        ticket_ids.update(commit_ticket_ids)
        
        # From activities
        activity_ticket_ids = TicketActivity.objects.filter(
            user=self.user,
            activity_at__gte=since,
            activity_at__lte=until,
        ).values_list('ticket_id', flat=True)
        ticket_ids.update(activity_ticket_ids)
        
        # From worklogs
        worklog_ticket_ids = Worklog.objects.filter(
            user=self.user,
            started_at__gte=since,
            started_at__lte=until,
        ).values_list('ticket_id', flat=True)
        ticket_ids.update(worklog_ticket_ids)
        
        total_tickets = len(ticket_ids)
        
        # Tickets completed (moved to Done/Closed)
        tickets_completed = TicketActivity.objects.filter(
            user=self.user,
            activity_type='status_change',
            activity_at__gte=since,
            activity_at__lte=until,
            to_status__iregex=r'(done|closed|resolved|complete)',
        ).values('ticket_id').distinct().count()
        
        # Total time logged
        total_time = Worklog.objects.filter(
            user=self.user,
            started_at__gte=since,
            started_at__lte=until,
        ).aggregate(total=Sum('time_spent_seconds'))['total'] or 0
        
        # Non-code activities (status changes without commits)
        non_code_activities = TicketActivity.objects.filter(
            user=self.user,
            activity_type='status_change',
            activity_at__gte=since,
            activity_at__lte=until,
        ).exclude(
            ticket__commits__committed_at__gte=since,
            ticket__commits__committed_at__lte=until,
        ).count()
        
        return {
            'total_commits': total_commits,
            'unlinked_commits': unlinked_commits,
            'total_tickets': total_tickets,
            'tickets_completed': tickets_completed,
            'total_time_logged_seconds': total_time,
            'total_time_logged_display': self._format_time(total_time),
            'non_code_activities': non_code_activities,
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
    
    def _get_tickets_data(
        self,
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        """Get detailed data for each ticket worked on."""
        # Get all ticket IDs with activity
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
        
        tickets_data = []
        
        for ticket_id in ticket_ids:
            ticket = Ticket.objects.get(id=ticket_id)
            
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
            
            # Get comments
            comments = TicketActivity.objects.filter(
                user=self.user,
                ticket=ticket,
                activity_type='comment',
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
            
            total_time = worklogs.aggregate(
                total=Sum('time_spent_seconds')
            )['total'] or 0
            
            # Determine tags
            tags = []
            if commits.count() == 0 and (status_changes.count() > 0 or worklogs.count() > 0):
                tags.append('non-code-activity')
            
            tickets_data.append({
                'id': str(ticket.id),
                'key': ticket.key,
                'title': ticket.title,
                'status': ticket.status,
                'url': ticket.url,
                'commits_count': commits.count(),
                'commits': [
                    {
                        'sha': c.sha[:7],
                        'message': c.message[:100],
                        'committed_at': c.committed_at.isoformat(),
                    }
                    for c in commits[:10]  # Limit to 10
                ],
                'status_changes': [
                    {
                        'from': sc.from_status,
                        'to': sc.to_status,
                        'at': sc.activity_at.isoformat(),
                    }
                    for sc in status_changes
                ],
                'comments_count': comments.count(),
                'time_logged_seconds': total_time,
                'time_logged_display': self._format_time(total_time),
                'tags': tags,
            })
        
        # Sort by commits count (most active first)
        tickets_data.sort(key=lambda x: x['commits_count'], reverse=True)
        
        return tickets_data
    
    def _get_unlinked_commits(
        self,
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        """Get commits without ticket references."""
        commits = Commit.objects.filter(
            user=self.user,
            committed_at__gte=since,
            committed_at__lte=until,
            is_unlinked=True,
        ).select_related('repository')
        
        return [
            {
                'sha': c.sha[:7],
                'message': c.message[:100],
                'repository': c.repository.full_name,
                'committed_at': c.committed_at.isoformat(),
                'url': c.url,
                'tag': 'unlinked-work',
            }
            for c in commits
        ]
    
    def _generate_markdown_report(self, report_data: Dict[str, Any]) -> str:
        """Generate a markdown formatted report."""
        lines = []
        
        date_range = report_data['date_range']
        stats = report_data['stats']
        
        lines.append(f"# Work Report: {date_range['start']} to {date_range['end']}")
        lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append(report_data.get('summary', 'No summary available.'))
        lines.append("")
        
        # Statistics
        lines.append("## Statistics")
        lines.append(f"- **Tickets Worked On:** {stats['total_tickets']}")
        lines.append(f"- **Commits Made:** {stats['total_commits']}")
        lines.append(f"- **Tickets Completed:** {stats['tickets_completed']}")
        lines.append(f"- **Time Logged:** {stats['total_time_logged_display']}")
        lines.append(f"- **Unlinked Commits:** {stats['unlinked_commits']}")
        lines.append(f"- **Non-Code Activities:** {stats['non_code_activities']}")
        lines.append("")
        
        # Tickets
        if report_data['tickets']:
            lines.append("## Tickets")
            for ticket in report_data['tickets'][:10]:
                tags_str = ' '.join([f"`{t}`" for t in ticket.get('tags', [])])
                lines.append(f"### [{ticket['key']}]({ticket['url']}): {ticket['title']}")
                lines.append(f"**Status:** {ticket['status']} | **Commits:** {ticket['commits_count']} | **Time:** {ticket['time_logged_display']} {tags_str}")
                
                if ticket['status_changes']:
                    for sc in ticket['status_changes']:
                        lines.append(f"  - Status: {sc['from']} → {sc['to']}")
                
                lines.append("")
        
        # Unlinked Commits
        if report_data['unlinked_commits']:
            lines.append("## Unlinked Work")
            lines.append("*Commits without Jira ticket references:*")
            lines.append("")
            for commit in report_data['unlinked_commits'][:10]:
                lines.append(f"- `{commit['sha']}` {commit['message']} ({commit['repository']})")
            lines.append("")
        
        # Hygiene Alerts
        if report_data['hygiene']['total_alerts'] > 0:
            lines.append("## Hygiene Alerts")
            lines.append(f"*{report_data['hygiene']['total_alerts']} issues detected*")
            lines.append("")
            for alert in report_data['hygiene']['alerts'][:5]:
                lines.append(f"- **{alert['title']}**: {alert['description']}")
            lines.append("")
        
        # Effort Analysis
        effort = report_data['effort_analysis']
        if effort['summary']['fast_wins_count'] > 0 or effort['summary']['high_effort_low_output_count'] > 0:
            lines.append("## Effort Analysis")
            if effort['summary']['fast_wins_count'] > 0:
                lines.append(f"✅ **Fast Wins:** {effort['summary']['fast_wins_count']} tickets")
            if effort['summary']['high_effort_low_output_count'] > 0:
                lines.append(f"⚠️ **High Effort, Low Output:** {effort['summary']['high_effort_low_output_count']} tickets")
            if effort['summary']['stalled_count'] > 0:
                lines.append(f"🔄 **Stalled:** {effort['summary']['stalled_count']} tickets")
            lines.append("")
        
        lines.append("---")
        lines.append(f"*Generated on {timezone.now().strftime('%Y-%m-%d %H:%M UTC')}*")
        
        return '\n'.join(lines)
    
    def create_weekly_report(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> WeeklyReport:
        """Create and store a weekly report."""
        # Generate report data
        report_data = self.generate_report(start_date, end_date, sync_first=True)
        
        # Create or update weekly report record
        weekly_report, created = WeeklyReport.objects.update_or_create(
            user=self.user,
            start_date=start_date.date(),
            end_date=end_date.date(),
            defaults={
                'total_tickets': report_data['stats']['total_tickets'],
                'total_commits': report_data['stats']['total_commits'],
                'tickets_completed': report_data['stats']['tickets_completed'],
                'total_time_logged_seconds': report_data['stats']['total_time_logged_seconds'],
                'unlinked_commits': report_data['stats']['unlinked_commits'],
                'non_code_activities': report_data['stats']['non_code_activities'],
                'summary_text': report_data['summary'],
                'markdown_report': report_data['markdown'],
                'report_data': report_data,
            }
        )
        
        return weekly_report
    
    def get_last_week_report(self) -> Optional[WeeklyReport]:
        """Get the most recent weekly report."""
        return WeeklyReport.objects.filter(user=self.user).first()
