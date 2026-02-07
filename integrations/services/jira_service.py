"""
Jira integration service for fetching tickets, activities, and worklogs.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import requests
from django.utils import timezone
from django.conf import settings

from core.models import (
    User, OAuthToken, JiraProject, Ticket, 
    TicketActivity, Worklog
)
from authentication.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


class JiraService:
    """Service for interacting with Jira API."""
    
    BASE_URL = 'https://api.atlassian.com/ex/jira'
    
    def __init__(self, user: User):
        self.user = user
        self._access_token = None
        self._cloud_id = None
    
    def _get_oauth_token(self) -> OAuthToken:
        """Get OAuth token record for the user."""
        try:
            return OAuthToken.objects.get(user=self.user, provider='jira')
        except OAuthToken.DoesNotExist:
            raise ValueError("Jira not connected for this user")
    
    def _get_access_token(self) -> str:
        """Get decrypted access token, refreshing if needed."""
        oauth_token = self._get_oauth_token()
        
        # Check if token needs refresh
        if oauth_token.expires_at and oauth_token.expires_at <= timezone.now():
            self._refresh_token(oauth_token)
        
        if not self._access_token:
            self._access_token = decrypt_token(oauth_token.access_token_encrypted)
        
        return self._access_token
    
    def _get_cloud_id(self) -> str:
        """Get Jira cloud ID for API requests."""
        if not self._cloud_id:
            oauth_token = self._get_oauth_token()
            self._cloud_id = oauth_token.cloud_id
        
        if not self._cloud_id:
            raise ValueError("No Jira cloud ID found. Please reconnect Jira.")
        
        return self._cloud_id
    
    def _refresh_token(self, oauth_token: OAuthToken) -> None:
        """Refresh the access token."""
        refresh_token = decrypt_token(oauth_token.refresh_token_encrypted)
        
        if not refresh_token:
            raise ValueError("No refresh token available. Please reconnect Jira.")
        
        response = requests.post(
            'https://auth.atlassian.com/oauth/token',
            json={
                'grant_type': 'refresh_token',
                'client_id': settings.JIRA_CLIENT_ID,
                'client_secret': settings.JIRA_CLIENT_SECRET,
                'refresh_token': refresh_token,
            },
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code != 200:
            raise ValueError("Failed to refresh Jira token. Please reconnect.")
        
        token_data = response.json()
        
        oauth_token.access_token_encrypted = encrypt_token(token_data['access_token'])
        if 'refresh_token' in token_data:
            oauth_token.refresh_token_encrypted = encrypt_token(token_data['refresh_token'])
        oauth_token.expires_at = timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600))
        oauth_token.save()
        
        self._access_token = token_data['access_token']
    
    def _make_request(
        self, 
        endpoint: str, 
        method: str = 'GET', 
        params: dict = None,
        json_data: dict = None,
    ) -> Any:
        """Make authenticated request to Jira API."""
        cloud_id = self._get_cloud_id()
        url = f"{self.BASE_URL}/{cloud_id}{endpoint}"
        
        headers = {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        response = requests.request(
            method, url, headers=headers, params=params, json=json_data
        )
        
        if response.status_code == 401:
            raise ValueError("Jira authentication failed")
        
        response.raise_for_status()
        
        if response.content:
            return response.json()
        return {}
    
    def get_projects(self) -> List[Dict]:
        """Get all accessible Jira projects."""
        response = self._make_request('/rest/api/3/project/search')
        return response.get('values', [])
    
    def sync_projects(self) -> List[JiraProject]:
        """Sync user's Jira projects."""
        projects_data = self.get_projects()
        cloud_id = self._get_cloud_id()
        projects = []
        
        for project_data in projects_data:
            project, created = JiraProject.objects.update_or_create(
                user=self.user,
                jira_id=project_data['id'],
                cloud_id=cloud_id,
                defaults={
                    'key': project_data['key'],
                    'name': project_data['name'],
                }
            )
            projects.append(project)
        
        return projects
    
    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: List[str] = None,
    ) -> Dict:
        """Search issues using JQL."""
        if fields is None:
            fields = [
                'summary', 'status', 'issuetype', 'priority',
                'assignee', 'reporter', 'created', 'updated',
                'description', 'worklog', 'comment', 'changelog'
            ]
        
        params = {
            'jql': jql,
            'startAt': start_at,
            'maxResults': max_results,
            'fields': ','.join(fields),
            'expand': 'changelog',
        }
        
        return self._make_request('/rest/api/3/search', params=params)
    
    def get_issues_for_date_range(
        self,
        project_keys: List[str],
        since: datetime,
        until: datetime,
    ) -> List[Dict]:
        """Get issues updated within a date range."""
        since_str = since.strftime('%Y-%m-%d')
        until_str = until.strftime('%Y-%m-%d')
        
        project_filter = ' OR '.join([f'project = {key}' for key in project_keys])
        jql = f"({project_filter}) AND updated >= '{since_str}' AND updated <= '{until_str}' ORDER BY updated DESC"
        
        all_issues = []
        start_at = 0
        
        while True:
            response = self.search_issues(jql, start_at=start_at)
            issues = response.get('issues', [])
            all_issues.extend(issues)
            
            total = response.get('total', 0)
            if start_at + len(issues) >= total:
                break
            
            start_at += len(issues)
        
        return all_issues
    
    def get_issue_by_key(self, issue_key: str) -> Optional[Dict]:
        """Get a single issue by key."""
        try:
            return self._make_request(
                f'/rest/api/3/issue/{issue_key}',
                params={'expand': 'changelog'}
            )
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def sync_ticket(self, issue_data: Dict, project: JiraProject = None) -> Ticket:
        """Create or update a ticket from Jira issue data."""
        fields = issue_data.get('fields', {})
        
        # Get or find project
        if not project:
            project_data = fields.get('project', {})
            project = JiraProject.objects.filter(
                user=self.user,
                key=project_data.get('key')
            ).first()
        
        # Parse dates
        created_at = datetime.fromisoformat(
            fields.get('created', '').replace('Z', '+00:00')
        ) if fields.get('created') else timezone.now()
        
        updated_at = datetime.fromisoformat(
            fields.get('updated', '').replace('Z', '+00:00')
        ) if fields.get('updated') else timezone.now()
        
        # Build Jira URL
        cloud_id = self._get_cloud_id()
        site_url = f"https://{self.user.email.split('@')[0]}.atlassian.net"
        issue_url = f"{site_url}/browse/{issue_data.get('key')}"
        
        ticket, created = Ticket.objects.update_or_create(
            user=self.user,
            jira_id=issue_data['id'],
            defaults={
                'project': project,
                'key': issue_data.get('key'),
                'title': fields.get('summary', 'No title'),
                'description': self._extract_text_from_adf(fields.get('description')),
                'status': fields.get('status', {}).get('name', 'Unknown'),
                'issue_type': fields.get('issuetype', {}).get('name', 'Unknown'),
                'priority': fields.get('priority', {}).get('name') if fields.get('priority') else None,
                'assignee': fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None,
                'reporter': fields.get('reporter', {}).get('displayName') if fields.get('reporter') else None,
                'url': issue_url,
                'created_at_jira': created_at,
                'updated_at_jira': updated_at,
            }
        )
        
        return ticket
    
    def _extract_text_from_adf(self, adf_content: Dict) -> str:
        """Extract plain text from Atlassian Document Format."""
        if not adf_content:
            return ''
        
        if isinstance(adf_content, str):
            return adf_content
        
        text_parts = []
        
        def extract_text(node):
            if isinstance(node, dict):
                if node.get('type') == 'text':
                    text_parts.append(node.get('text', ''))
                for child in node.get('content', []):
                    extract_text(child)
            elif isinstance(node, list):
                for item in node:
                    extract_text(item)
        
        extract_text(adf_content)
        return ' '.join(text_parts)
    
    def sync_ticket_activities(
        self,
        ticket: Ticket,
        since: datetime,
        until: datetime,
    ) -> List[TicketActivity]:
        """Sync activities (status changes, comments) for a ticket."""
        issue_data = self.get_issue_by_key(ticket.key)
        if not issue_data:
            return []
        
        activities = []
        
        # Process changelog (status changes, field changes)
        changelog = issue_data.get('changelog', {})
        for history in changelog.get('histories', []):
            created_at = datetime.fromisoformat(
                history.get('created', '').replace('Z', '+00:00')
            )
            
            # Filter by date range
            if not (since <= created_at <= until):
                continue
            
            author = history.get('author', {}).get('displayName', 'Unknown')
            
            for item in history.get('items', []):
                field = item.get('field', '')
                
                if field.lower() == 'status':
                    activity_type = 'status_change'
                else:
                    activity_type = 'field_change'
                
                activity, created = TicketActivity.objects.update_or_create(
                    user=self.user,
                    ticket=ticket,
                    jira_id=f"{history['id']}_{item.get('fieldId', field)}",
                    defaults={
                        'activity_type': activity_type,
                        'author': author,
                        'from_status': item.get('fromString') if activity_type == 'status_change' else None,
                        'to_status': item.get('toString') if activity_type == 'status_change' else None,
                        'field_name': field if activity_type == 'field_change' else None,
                        'from_value': item.get('fromString') if activity_type == 'field_change' else None,
                        'to_value': item.get('toString') if activity_type == 'field_change' else None,
                        'activity_at': created_at,
                    }
                )
                activities.append(activity)
        
        # Process comments
        fields = issue_data.get('fields', {})
        comments = fields.get('comment', {}).get('comments', [])
        
        for comment in comments:
            created_at = datetime.fromisoformat(
                comment.get('created', '').replace('Z', '+00:00')
            )
            
            if not (since <= created_at <= until):
                continue
            
            activity, created = TicketActivity.objects.update_or_create(
                user=self.user,
                ticket=ticket,
                jira_id=comment['id'],
                defaults={
                    'activity_type': 'comment',
                    'author': comment.get('author', {}).get('displayName', 'Unknown'),
                    'comment_body': self._extract_text_from_adf(comment.get('body')),
                    'activity_at': created_at,
                }
            )
            activities.append(activity)
        
        return activities
    
    def get_worklogs(self, issue_key: str) -> List[Dict]:
        """Get worklogs for an issue."""
        response = self._make_request(f'/rest/api/3/issue/{issue_key}/worklog')
        return response.get('worklogs', [])
    
    def sync_worklogs(
        self,
        ticket: Ticket,
        since: datetime,
        until: datetime,
    ) -> List[Worklog]:
        """Sync worklogs for a ticket within a date range."""
        worklogs_data = self.get_worklogs(ticket.key)
        worklogs = []
        
        for worklog_data in worklogs_data:
            started_at = datetime.fromisoformat(
                worklog_data.get('started', '').replace('Z', '+00:00')
            )
            
            # Filter by date range
            if not (since <= started_at <= until):
                continue
            
            worklog, created = Worklog.objects.update_or_create(
                user=self.user,
                jira_id=worklog_data['id'],
                defaults={
                    'ticket': ticket,
                    'author': worklog_data.get('author', {}).get('displayName', 'Unknown'),
                    'time_spent_seconds': worklog_data.get('timeSpentSeconds', 0),
                    'time_spent_display': worklog_data.get('timeSpent', '0m'),
                    'comment': self._extract_text_from_adf(worklog_data.get('comment')),
                    'started_at': started_at,
                }
            )
            worklogs.append(worklog)
        
        return worklogs
    
    def sync_all_for_date_range(
        self,
        since: datetime,
        until: datetime,
        project_keys: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Sync all Jira data for a date range.
        
        Returns summary of synced data.
        """
        # Get tracked projects if not specified
        if not project_keys:
            projects = JiraProject.objects.filter(user=self.user, is_tracked=True)
            project_keys = [p.key for p in projects]
        
        if not project_keys:
            return {'tickets': [], 'activities': [], 'worklogs': []}
        
        # Get issues
        issues_data = self.get_issues_for_date_range(project_keys, since, until)
        
        all_tickets = []
        all_activities = []
        all_worklogs = []
        
        for issue_data in issues_data:
            # Sync ticket
            ticket = self.sync_ticket(issue_data)
            all_tickets.append(ticket)
            
            # Sync activities
            activities = self.sync_ticket_activities(ticket, since, until)
            all_activities.extend(activities)
            
            # Sync worklogs
            worklogs = self.sync_worklogs(ticket, since, until)
            all_worklogs.extend(worklogs)
        
        # Update project sync timestamps
        JiraProject.objects.filter(user=self.user, key__in=project_keys).update(
            last_synced_at=timezone.now()
        )
        
        logger.info(
            f"Synced {len(all_tickets)} tickets, "
            f"{len(all_activities)} activities, "
            f"{len(all_worklogs)} worklogs for user {self.user.email}"
        )
        
        return {
            'tickets': all_tickets,
            'activities': all_activities,
            'worklogs': all_worklogs,
        }
    
    def get_ticket_by_keys(self, keys: List[str]) -> List[Ticket]:
        """Get or fetch tickets by their keys."""
        tickets = []
        
        for key in keys:
            # Check local database first
            ticket = Ticket.objects.filter(user=self.user, key=key).first()
            
            if not ticket:
                # Fetch from Jira
                issue_data = self.get_issue_by_key(key)
                if issue_data:
                    ticket = self.sync_ticket(issue_data)
            
            if ticket:
                tickets.append(ticket)
        
        return tickets
