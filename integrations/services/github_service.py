"""
GitHub integration service for fetching commits, PRs, and repositories.
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
import requests
from django.utils import timezone

from core.models import User, OAuthToken, Repository, Commit, Ticket
from authentication.encryption import decrypt_token

logger = logging.getLogger(__name__)


class GitHubService:
    """Service for interacting with GitHub API."""
    
    BASE_URL = 'https://api.github.com'
    TICKET_PATTERN = re.compile(r'([A-Z]+-\d+)')
    
    def __init__(self, user: User):
        self.user = user
        self._access_token = None
    
    def _get_access_token(self) -> str:
        """Get decrypted access token for the user."""
        if not self._access_token:
            try:
                oauth_token = OAuthToken.objects.get(user=self.user, provider='github')
                self._access_token = decrypt_token(oauth_token.access_token_encrypted)
            except OAuthToken.DoesNotExist:
                raise ValueError("GitHub not connected for this user")
        return self._access_token
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None) -> Any:
        """Make authenticated request to GitHub API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        }
        
        response = requests.request(method, url, headers=headers, params=params)
        
        if response.status_code == 401:
            raise ValueError("GitHub authentication failed")
        
        response.raise_for_status()
        return response.json()
    
    def get_user_info(self) -> Dict:
        """Get authenticated user information."""
        return self._make_request('/user')
    
    def get_repositories(self, include_private: bool = True) -> List[Dict]:
        """Get user's repositories."""
        params = {
            'visibility': 'all' if include_private else 'public',
            'affiliation': 'owner,collaborator,organization_member',
            'sort': 'updated',
            'per_page': 100,
        }
        return self._make_request('/user/repos', params=params)
    
    def sync_repositories(self) -> List[Repository]:
        """Sync user's repositories from GitHub."""
        repos_data = self.get_repositories()
        repositories = []
        
        for repo_data in repos_data:
            repo, created = Repository.objects.update_or_create(
                user=self.user,
                github_id=repo_data['id'],
                defaults={
                    'name': repo_data['name'],
                    'full_name': repo_data['full_name'],
                    'description': repo_data.get('description'),
                    'url': repo_data['html_url'],
                    'is_private': repo_data['private'],
                    'default_branch': repo_data.get('default_branch', 'main'),
                }
            )
            repositories.append(repo)
        
        return repositories
    
    def get_commits(
        self,
        repo_full_name: str,
        since: datetime,
        until: datetime,
        author: str = None,
        branch: str = None,
    ) -> List[Dict]:
        """
        Get commits for a repository within a date range.
        
        Args:
            repo_full_name: Full repository name (owner/repo)
            since: Start date
            until: End date
            author: Filter by author email/username
            branch: Branch name (default: default branch)
        """
        params = {
            'since': since.isoformat(),
            'until': until.isoformat(),
            'per_page': 100,
        }
        
        if author:
            params['author'] = author
        
        if branch:
            params['sha'] = branch
        
        endpoint = f"/repos/{repo_full_name}/commits"
        commits = []
        
        try:
            response_data = self._make_request(endpoint, params=params)
            commits.extend(response_data)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Repository {repo_full_name} not found or no access")
            else:
                raise
        
        return commits
    
    def get_commit_details(self, repo_full_name: str, sha: str) -> Dict:
        """Get detailed commit information including stats."""
        return self._make_request(f"/repos/{repo_full_name}/commits/{sha}")
    
    def extract_ticket_keys(self, commit_message: str) -> List[str]:
        """Extract Jira ticket keys from commit message."""
        matches = self.TICKET_PATTERN.findall(commit_message)
        return list(set(matches))  # Remove duplicates
    
    def sync_commits(
        self,
        repository: Repository,
        since: datetime,
        until: datetime,
        author_email: str = None,
    ) -> List[Commit]:
        """
        Sync commits for a repository within a date range.
        
        Returns list of Commit objects created or updated.
        """
        # Get user's GitHub info for author filter
        if not author_email:
            try:
                user_info = self.get_user_info()
                author_email = user_info.get('email')
            except Exception:
                pass
        
        commits_data = self.get_commits(
            repo_full_name=repository.full_name,
            since=since,
            until=until,
            author=author_email,
        )
        
        synced_commits = []
        
        for commit_data in commits_data:
            commit_info = commit_data.get('commit', {})
            author_info = commit_info.get('author', {})
            
            # Extract ticket keys from message
            message = commit_info.get('message', '')
            ticket_keys = self.extract_ticket_keys(message)
            
            # Try to find matching ticket
            ticket = None
            if ticket_keys:
                ticket = Ticket.objects.filter(
                    user=self.user,
                    key__in=ticket_keys
                ).first()
            
            is_unlinked = len(ticket_keys) == 0
            
            # Parse commit date
            commit_date_str = author_info.get('date')
            if commit_date_str:
                committed_at = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
            else:
                committed_at = timezone.now()
            
            # Get commit stats if available
            stats = commit_data.get('stats', {})
            
            commit_obj, created = Commit.objects.update_or_create(
                user=self.user,
                repository=repository,
                sha=commit_data['sha'],
                defaults={
                    'ticket': ticket,
                    'message': message,
                    'author_name': author_info.get('name', 'Unknown'),
                    'author_email': author_info.get('email', ''),
                    'committed_at': committed_at,
                    'url': commit_data.get('html_url', ''),
                    'additions': stats.get('additions', 0),
                    'deletions': stats.get('deletions', 0),
                    'files_changed': stats.get('total', 0),
                    'extracted_ticket_keys': ticket_keys,
                    'is_unlinked': is_unlinked,
                }
            )
            synced_commits.append(commit_obj)
        
        # Update repository last synced timestamp
        repository.last_synced_at = timezone.now()
        repository.save()
        
        return synced_commits
    
    def get_pull_requests(
        self,
        repo_full_name: str,
        state: str = 'all',
        since: datetime = None,
    ) -> List[Dict]:
        """Get pull requests for a repository."""
        params = {
            'state': state,
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 100,
        }
        
        prs = self._make_request(f"/repos/{repo_full_name}/pulls", params=params)
        
        # Filter by date if provided
        if since:
            prs = [
                pr for pr in prs
                if datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00')) >= since
            ]
        
        return prs
    
    def sync_all_tracked_repos(
        self,
        since: datetime,
        until: datetime,
    ) -> Dict[str, List[Commit]]:
        """
        Sync commits for all tracked repositories.
        
        Returns dict mapping repo full_name to list of commits.
        """
        results = {}
        
        tracked_repos = Repository.objects.filter(
            user=self.user,
            is_tracked=True
        )
        
        for repo in tracked_repos:
            try:
                commits = self.sync_commits(repo, since, until)
                results[repo.full_name] = commits
                logger.info(f"Synced {len(commits)} commits from {repo.full_name}")
            except Exception as e:
                logger.error(f"Error syncing {repo.full_name}: {e}")
                results[repo.full_name] = []
        
        return results
