"""
Integration URL routes.
"""

from django.urls import path
from . import views

urlpatterns = [
    # GitHub
    path('github/repositories/', views.GitHubRepositoriesView.as_view(), name='github_repositories'),
    path('github/repositories/sync/', views.GitHubSyncRepositoriesView.as_view(), name='github_sync_repos'),
    path('github/repositories/<uuid:repo_id>/toggle/', views.GitHubToggleTrackingView.as_view(), name='github_toggle_tracking'),
    path('github/commits/', views.CommitsListView.as_view(), name='commits_list'),
    path('github/commits/sync/', views.GitHubSyncCommitsView.as_view(), name='github_sync_commits'),
    
    # Jira
    path('jira/projects/', views.JiraProjectsView.as_view(), name='jira_projects'),
    path('jira/projects/sync/', views.JiraSyncProjectsView.as_view(), name='jira_sync_projects'),
    path('jira/projects/<uuid:project_id>/toggle/', views.JiraToggleTrackingView.as_view(), name='jira_toggle_tracking'),
    path('jira/sync/', views.JiraSyncDataView.as_view(), name='jira_sync_data'),
    path('jira/tickets/', views.TicketsListView.as_view(), name='tickets_list'),
    path('jira/tickets/<str:key>/', views.TicketDetailView.as_view(), name='ticket_detail'),
]
