"""
Celery tasks for authentication and token management.
"""

import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings
import requests

logger = logging.getLogger(__name__)


@shared_task
def refresh_expiring_tokens():
    """Refresh Jira tokens that are about to expire."""
    from core.models import OAuthToken
    from authentication.encryption import decrypt_token, encrypt_token
    
    # Find tokens expiring in the next hour
    expiry_threshold = timezone.now() + timedelta(hours=1)
    
    expiring_tokens = OAuthToken.objects.filter(
        provider='jira',
        expires_at__lte=expiry_threshold,
        refresh_token_encrypted__isnull=False,
    )
    
    logger.info(f"Found {expiring_tokens.count()} Jira tokens to refresh")
    
    refreshed = 0
    failed = 0
    
    for oauth_token in expiring_tokens:
        try:
            refresh_token = decrypt_token(oauth_token.refresh_token_encrypted)
            
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
            
            if response.status_code == 200:
                token_data = response.json()
                
                oauth_token.access_token_encrypted = encrypt_token(token_data['access_token'])
                if 'refresh_token' in token_data:
                    oauth_token.refresh_token_encrypted = encrypt_token(token_data['refresh_token'])
                oauth_token.expires_at = timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600))
                oauth_token.save()
                
                refreshed += 1
                logger.info(f"Refreshed token for user {oauth_token.user.email}")
            else:
                failed += 1
                logger.error(f"Failed to refresh token for user {oauth_token.user.email}: {response.text}")
        
        except Exception as e:
            failed += 1
            logger.exception(f"Error refreshing token for user {oauth_token.user.email}: {e}")
    
    return {
        'refreshed': refreshed,
        'failed': failed,
        'total': expiring_tokens.count(),
    }
