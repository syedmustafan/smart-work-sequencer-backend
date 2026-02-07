"""
API views for GitHub and Jira integrations.
"""

import logging
from datetime import datetime
from rest_framework import status, views, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Repository, JiraProject, Commit, Ticket
from .serializers import (
    RepositorySerializer, JiraProjectSerializer, 
    CommitSerializer, TicketSerializer, SyncRequestSerializer
)
from .services import GitHubService, JiraService

logger = logging.getLogger(__name__)


# ==================== GitHub Views ====================

class GitHubRepositoriesView(generics.ListAPIView):
    """List user's GitHub repositories."""
    permission_classes = [IsAuthenticated]
    serializer_class = RepositorySerializer
    
    def get_queryset(self):
        return Repository.objects.filter(user=self.request.user)


class GitHubSyncRepositoriesView(views.APIView):
    """Sync repositories from GitHub."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        if not request.user.github_connected:
            return Response(
                {'error': 'GitHub not connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = GitHubService(request.user)
            repos = service.sync_repositories()
            return Response({
                'message': f'Synced {len(repos)} repositories',
                'repositories': RepositorySerializer(repos, many=True).data
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error syncing repositories: {e}")
            return Response(
                {'error': 'Failed to sync repositories'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GitHubToggleTrackingView(views.APIView):
    """Toggle repository tracking."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, repo_id):
        try:
            repo = Repository.objects.get(id=repo_id, user=request.user)
            repo.is_tracked = not repo.is_tracked
            repo.save()
            return Response(RepositorySerializer(repo).data)
        except Repository.DoesNotExist:
            return Response(
                {'error': 'Repository not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class GitHubSyncCommitsView(views.APIView):
    """Sync commits from GitHub for a date range."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = SyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if not request.user.github_connected:
            return Response(
                {'error': 'GitHub not connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = GitHubService(request.user)
            since = serializer.validated_data['since']
            until = serializer.validated_data['until']
            
            results = service.sync_all_tracked_repos(since, until)
            
            total_commits = sum(len(commits) for commits in results.values())
            
            return Response({
                'message': f'Synced {total_commits} commits from {len(results)} repositories',
                'by_repository': {
                    repo: len(commits) for repo, commits in results.items()
                }
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error syncing commits: {e}")
            return Response(
                {'error': 'Failed to sync commits'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CommitsListView(generics.ListAPIView):
    """List commits with optional filters."""
    permission_classes = [IsAuthenticated]
    serializer_class = CommitSerializer
    
    def get_queryset(self):
        queryset = Commit.objects.filter(user=self.request.user)
        
        # Filter by date range
        since = self.request.query_params.get('since')
        until = self.request.query_params.get('until')
        
        if since:
            queryset = queryset.filter(committed_at__gte=since)
        if until:
            queryset = queryset.filter(committed_at__lte=until)
        
        # Filter by repository
        repo_id = self.request.query_params.get('repository')
        if repo_id:
            queryset = queryset.filter(repository_id=repo_id)
        
        # Filter by unlinked
        unlinked = self.request.query_params.get('unlinked')
        if unlinked and unlinked.lower() == 'true':
            queryset = queryset.filter(is_unlinked=True)
        
        return queryset.select_related('repository', 'ticket')


# ==================== Jira Views ====================

class JiraProjectsView(generics.ListAPIView):
    """List user's Jira projects."""
    permission_classes = [IsAuthenticated]
    serializer_class = JiraProjectSerializer
    
    def get_queryset(self):
        return JiraProject.objects.filter(user=self.request.user)


class JiraSyncProjectsView(views.APIView):
    """Sync projects from Jira."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        if not request.user.jira_connected:
            return Response(
                {'error': 'Jira not connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = JiraService(request.user)
            projects = service.sync_projects()
            return Response({
                'message': f'Synced {len(projects)} projects',
                'projects': JiraProjectSerializer(projects, many=True).data
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error syncing projects: {e}")
            return Response(
                {'error': 'Failed to sync projects'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class JiraToggleTrackingView(views.APIView):
    """Toggle project tracking."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, project_id):
        try:
            project = JiraProject.objects.get(id=project_id, user=request.user)
            project.is_tracked = not project.is_tracked
            project.save()
            return Response(JiraProjectSerializer(project).data)
        except JiraProject.DoesNotExist:
            return Response(
                {'error': 'Project not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class JiraSyncDataView(views.APIView):
    """Sync Jira data (tickets, activities, worklogs) for a date range."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = SyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if not request.user.jira_connected:
            return Response(
                {'error': 'Jira not connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = JiraService(request.user)
            since = serializer.validated_data['since']
            until = serializer.validated_data['until']
            project_keys = serializer.validated_data.get('project_keys')
            
            results = service.sync_all_for_date_range(since, until, project_keys)
            
            return Response({
                'message': 'Jira data synced successfully',
                'tickets_synced': len(results['tickets']),
                'activities_synced': len(results['activities']),
                'worklogs_synced': len(results['worklogs']),
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error syncing Jira data: {e}")
            return Response(
                {'error': 'Failed to sync Jira data'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TicketsListView(generics.ListAPIView):
    """List tickets with optional filters."""
    permission_classes = [IsAuthenticated]
    serializer_class = TicketSerializer
    
    def get_queryset(self):
        queryset = Ticket.objects.filter(user=self.request.user)
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status__iexact=status_filter)
        
        # Filter by date range (updated)
        since = self.request.query_params.get('since')
        until = self.request.query_params.get('until')
        
        if since:
            queryset = queryset.filter(updated_at_jira__gte=since)
        if until:
            queryset = queryset.filter(updated_at_jira__lte=until)
        
        return queryset.select_related('project')


class TicketDetailView(generics.RetrieveAPIView):
    """Get detailed ticket information."""
    permission_classes = [IsAuthenticated]
    serializer_class = TicketSerializer
    lookup_field = 'key'
    
    def get_queryset(self):
        return Ticket.objects.filter(user=self.request.user)
