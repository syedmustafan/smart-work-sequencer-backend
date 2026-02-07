"""
AI service for generating smart summaries using OpenAI.
"""

import logging
from typing import Dict, Any
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered summaries and insights."""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def generate_work_summary(self, report_data: Dict[str, Any]) -> str:
        """
        Generate a natural language summary of work done.
        
        Args:
            report_data: Dictionary containing report statistics and details
        
        Returns:
            Natural language summary string
        """
        # Extract key metrics
        stats = report_data.get('stats', {})
        date_range = report_data.get('date_range', {})
        
        prompt = f"""Based on the following developer work data, generate a concise, professional summary paragraph:

Date Range: {date_range.get('start', 'N/A')} to {date_range.get('end', 'N/A')}

Statistics:
- Total tickets worked on: {stats.get('total_tickets', 0)}
- Total commits made: {stats.get('total_commits', 0)}
- Tickets completed (moved to Done): {stats.get('tickets_completed', 0)}
- Total time logged: {stats.get('total_time_logged_display', '0h')}
- Unlinked commits (no ticket reference): {stats.get('unlinked_commits', 0)}
- Non-code activities: {stats.get('non_code_activities', 0)}

Top Tickets Worked On:
{self._format_tickets(report_data.get('tickets', [])[:5])}

Generate a 2-3 sentence summary that sounds natural and informative. Focus on productivity and accomplishments. Mention any concerns like unlinked commits if they exist."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that summarizes developer work activity. Be concise, professional, and encouraging."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Error generating AI summary: {e}")
            return self._generate_fallback_summary(stats, date_range)
    
    def _format_tickets(self, tickets: list) -> str:
        """Format ticket list for prompt."""
        if not tickets:
            return "No tickets found"
        
        lines = []
        for t in tickets:
            lines.append(f"- {t.get('key', 'N/A')}: {t.get('title', 'No title')[:50]} ({t.get('commits_count', 0)} commits)")
        return '\n'.join(lines)
    
    def _generate_fallback_summary(self, stats: Dict, date_range: Dict) -> str:
        """Generate a basic summary without AI."""
        start = date_range.get('start', 'the start')
        end = date_range.get('end', 'the end')
        
        parts = [f"Between {start} and {end}"]
        
        if stats.get('total_tickets', 0) > 0:
            parts.append(f"you worked on {stats['total_tickets']} ticket(s)")
        
        if stats.get('total_commits', 0) > 0:
            parts.append(f"made {stats['total_commits']} commit(s)")
        
        if stats.get('tickets_completed', 0) > 0:
            parts.append(f"completed {stats['tickets_completed']} ticket(s)")
        
        if stats.get('total_time_logged_display'):
            parts.append(f"logged {stats['total_time_logged_display']}")
        
        summary = ', '.join(parts[1:]) if len(parts) > 1 else "no significant activity was recorded"
        
        return f"{parts[0]}, {summary}."
    
    def generate_effort_analysis(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze effort vs output for a ticket.
        
        Returns classification: 'fast_win', 'high_effort_low_output', 'stalled', 'normal'
        """
        commits_count = ticket_data.get('commits_count', 0)
        time_logged_hours = ticket_data.get('time_logged_seconds', 0) / 3600
        status_changes = ticket_data.get('status_changes_count', 0)
        current_status = ticket_data.get('status', '').lower()
        
        classification = 'normal'
        insights = []
        
        # Fast win: completed quickly with minimal effort
        if current_status in ['done', 'closed', 'resolved']:
            if commits_count <= 3 and time_logged_hours <= 2:
                classification = 'fast_win'
                insights.append("Quick turnaround with minimal effort")
        
        # High effort, low output: lots of work but no movement
        elif commits_count > 5 and status_changes == 0:
            classification = 'high_effort_low_output'
            insights.append("Multiple commits but no status progress")
        
        elif time_logged_hours > 8 and status_changes == 0:
            classification = 'high_effort_low_output'
            insights.append("Significant time logged but no status movement")
        
        # Stalled: has activity but stuck
        elif commits_count > 0 or time_logged_hours > 0:
            if status_changes == 0 and current_status not in ['done', 'closed', 'resolved']:
                classification = 'stalled'
                insights.append("Work detected but ticket hasn't progressed")
        
        return {
            'classification': classification,
            'insights': insights,
            'metrics': {
                'commits': commits_count,
                'time_logged_hours': round(time_logged_hours, 1),
                'status_changes': status_changes,
            }
        }
    
    def generate_hygiene_recommendations(self, alerts: list) -> str:
        """Generate actionable recommendations based on hygiene alerts."""
        if not alerts:
            return "Great job! No hygiene issues detected."
        
        alert_summary = "\n".join([
            f"- {a.get('type', 'Unknown')}: {a.get('count', 0)} occurrence(s)"
            for a in alerts
        ])
        
        prompt = f"""Based on these code hygiene issues, provide 2-3 brief, actionable recommendations:

Issues Found:
{alert_summary}

Focus on practical steps to improve workflow hygiene. Be constructive and encouraging."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful dev productivity coach. Give brief, actionable advice."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return "Consider linking commits to Jira tickets and keeping ticket statuses up to date."
