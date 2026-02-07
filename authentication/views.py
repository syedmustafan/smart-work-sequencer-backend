"""
Authentication views for OAuth flows.
Simplified version without login/registration - uses session-based user identification.
"""

import logging
import uuid
from datetime import timedelta
from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import requests

from core.models import User, OAuthToken
from .encryption import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)


def get_or_create_session_user(request):
    """Get or create a user based on session."""
    session_user_id = request.session.get('user_id')
    
    if session_user_id:
        try:
            return User.objects.get(id=session_user_id)
        except User.DoesNotExist:
            pass
    
    # Create a new anonymous user
    user = User.objects.create(
        email=f"user_{uuid.uuid4().hex[:8]}@local.dev",
        username=f"Developer_{uuid.uuid4().hex[:6]}",
    )
    user.set_unusable_password()
    user.save()
    
    request.session['user_id'] = str(user.id)
    return user


# ==================== GitHub OAuth ====================

class GitHubAuthURLView(views.APIView):
    """Get GitHub OAuth authorization URL."""
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Get or create session user
        user = get_or_create_session_user(request)
        
        scopes = 'read:user repo read:org'
        state = str(user.id)
        
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={settings.GITHUB_CLIENT_ID}"
            f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
            f"&scope={scopes}"
            f"&state={state}"
        )
        
        return Response({'auth_url': auth_url})


class GitHubCallbackView(views.APIView):
    """Handle GitHub OAuth callback."""
    permission_classes = [AllowAny]
    
    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')  # User ID
        
        if not code:
            return redirect(f"{settings.FRONTEND_URL}/settings?error=github_auth_failed")
        
        try:
            # Exchange code for access token
            token_response = requests.post(
                'https://github.com/login/oauth/access_token',
                data={
                    'client_id': settings.GITHUB_CLIENT_ID,
                    'client_secret': settings.GITHUB_CLIENT_SECRET,
                    'code': code,
                    'redirect_uri': settings.GITHUB_REDIRECT_URI,
                },
                headers={'Accept': 'application/json'}
            )
            token_data = token_response.json()
            
            if 'error' in token_data:
                logger.error(f"GitHub OAuth error: {token_data}")
                return redirect(f"{settings.FRONTEND_URL}/settings?error=github_auth_failed")
            
            access_token = token_data.get('access_token')
            token_type = token_data.get('token_type', 'Bearer')
            scope = token_data.get('scope', '')
            
            # Get user from state
            user = User.objects.get(id=state)
            
            # Store encrypted token
            OAuthToken.objects.update_or_create(
                user=user,
                provider='github',
                defaults={
                    'access_token_encrypted': encrypt_token(access_token),
                    'token_type': token_type,
                    'scope': scope,
                    'expires_at': None,
                }
            )
            
            # Update user connection status
            user.github_connected = True
            user.save()
            
            return redirect(f"{settings.FRONTEND_URL}/settings?github=connected")
        
        except Exception as e:
            logger.exception(f"GitHub callback error: {e}")
            return redirect(f"{settings.FRONTEND_URL}/settings?error=github_auth_failed")


class GitHubDisconnectView(views.APIView):
    """Disconnect GitHub account."""
    permission_classes = [AllowAny]
    
    def post(self, request):
        session_user_id = request.session.get('user_id')
        if session_user_id:
            OAuthToken.objects.filter(user_id=session_user_id, provider='github').delete()
            try:
                user = User.objects.get(id=session_user_id)
                user.github_connected = False
                user.save()
            except User.DoesNotExist:
                pass
        return Response({'message': 'GitHub disconnected successfully'})


# ==================== Jira OAuth ====================

class JiraAuthURLView(views.APIView):
    """Get Jira OAuth authorization URL."""
    permission_classes = [AllowAny]
    
    def get(self, request):
        user = get_or_create_session_user(request)
        
        scopes = 'read:jira-work read:jira-user offline_access'
        state = str(user.id)
        
        auth_url = (
            f"https://auth.atlassian.com/authorize"
            f"?audience=api.atlassian.com"
            f"&client_id={settings.JIRA_CLIENT_ID}"
            f"&scope={scopes}"
            f"&redirect_uri={settings.JIRA_REDIRECT_URI}"
            f"&state={state}"
            f"&response_type=code"
            f"&prompt=consent"
        )
        
        return Response({'auth_url': auth_url})


class JiraCallbackView(views.APIView):
    """Handle Jira OAuth callback."""
    permission_classes = [AllowAny]
    
    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        
        if not code:
            return redirect(f"{settings.FRONTEND_URL}/settings?error=jira_auth_failed")
        
        try:
            # Exchange code for tokens
            token_response = requests.post(
                'https://auth.atlassian.com/oauth/token',
                json={
                    'grant_type': 'authorization_code',
                    'client_id': settings.JIRA_CLIENT_ID,
                    'client_secret': settings.JIRA_CLIENT_SECRET,
                    'code': code,
                    'redirect_uri': settings.JIRA_REDIRECT_URI,
                },
                headers={'Content-Type': 'application/json'}
            )
            token_data = token_response.json()
            
            if 'error' in token_data:
                logger.error(f"Jira OAuth error: {token_data}")
                return redirect(f"{settings.FRONTEND_URL}/settings?error=jira_auth_failed")
            
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 3600)
            scope = token_data.get('scope', '')
            
            # Get accessible resources (cloud IDs)
            resources_response = requests.get(
                'https://api.atlassian.com/oauth/token/accessible-resources',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            resources = resources_response.json()
            
            cloud_id = resources[0]['id'] if resources else None
            
            user = User.objects.get(id=state)
            
            # Store encrypted tokens
            OAuthToken.objects.update_or_create(
                user=user,
                provider='jira',
                defaults={
                    'access_token_encrypted': encrypt_token(access_token),
                    'refresh_token_encrypted': encrypt_token(refresh_token) if refresh_token else None,
                    'token_type': 'Bearer',
                    'scope': scope,
                    'cloud_id': cloud_id,
                    'expires_at': timezone.now() + timedelta(seconds=expires_in),
                }
            )
            
            user.jira_connected = True
            user.save()
            
            return redirect(f"{settings.FRONTEND_URL}/settings?jira=connected")
        
        except Exception as e:
            logger.exception(f"Jira callback error: {e}")
            return redirect(f"{settings.FRONTEND_URL}/settings?error=jira_auth_failed")


class JiraDisconnectView(views.APIView):
    """Disconnect Jira account."""
    permission_classes = [AllowAny]
    
    def post(self, request):
        session_user_id = request.session.get('user_id')
        if session_user_id:
            OAuthToken.objects.filter(user_id=session_user_id, provider='jira').delete()
            try:
                user = User.objects.get(id=session_user_id)
                user.jira_connected = False
                user.save()
            except User.DoesNotExist:
                pass
        return Response({'message': 'Jira disconnected successfully'})


class JiraRefreshTokenView(views.APIView):
    """Refresh Jira access token."""
    permission_classes = [AllowAny]
    
    def post(self, request):
        session_user_id = request.session.get('user_id')
        if not session_user_id:
            return Response(
                {'error': 'No session found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            oauth_token = OAuthToken.objects.get(user_id=session_user_id, provider='jira')
            refresh_token = decrypt_token(oauth_token.refresh_token_encrypted)
            
            if not refresh_token:
                return Response(
                    {'error': 'No refresh token available'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            token_response = requests.post(
                'https://auth.atlassian.com/oauth/token',
                json={
                    'grant_type': 'refresh_token',
                    'client_id': settings.JIRA_CLIENT_ID,
                    'client_secret': settings.JIRA_CLIENT_SECRET,
                    'refresh_token': refresh_token,
                },
                headers={'Content-Type': 'application/json'}
            )
            token_data = token_response.json()
            
            if 'error' in token_data:
                return Response(
                    {'error': 'Failed to refresh token'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            oauth_token.access_token_encrypted = encrypt_token(token_data['access_token'])
            if 'refresh_token' in token_data:
                oauth_token.refresh_token_encrypted = encrypt_token(token_data['refresh_token'])
            oauth_token.expires_at = timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600))
            oauth_token.save()
            
            return Response({'message': 'Token refreshed successfully'})
        
        except OAuthToken.DoesNotExist:
            return Response(
                {'error': 'No Jira connection found'},
                status=status.HTTP_404_NOT_FOUND
            )
