"""
Authentication URL routes.
"""

from django.urls import path
from . import views

urlpatterns = [
    # User auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('me/', views.MeView.as_view(), name='me'),
    path('connections/', views.ConnectionStatusView.as_view(), name='connections'),
    
    # GitHub OAuth
    path('github/', views.GitHubAuthURLView.as_view(), name='github_auth_url'),
    path('github/callback/', views.GitHubCallbackView.as_view(), name='github_callback'),
    path('github/disconnect/', views.GitHubDisconnectView.as_view(), name='github_disconnect'),
    
    # Jira OAuth
    path('jira/', views.JiraAuthURLView.as_view(), name='jira_auth_url'),
    path('jira/callback/', views.JiraCallbackView.as_view(), name='jira_callback'),
    path('jira/disconnect/', views.JiraDisconnectView.as_view(), name='jira_disconnect'),
    path('jira/refresh/', views.JiraRefreshTokenView.as_view(), name='jira_refresh'),
]
