"""
Custom authentication backends for the API.
"""

import jwt
from datetime import datetime, timedelta
from django.conf import settings
from rest_framework import authentication, exceptions
from core.models import User


class TokenAuthentication(authentication.BaseAuthentication):
    """JWT Token Authentication."""
    
    keyword = 'Bearer'
    
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header:
            return None
        
        try:
            auth_parts = auth_header.split()
            
            if len(auth_parts) != 2 or auth_parts[0] != self.keyword:
                return None
            
            token = auth_parts[1]
            payload = self.decode_token(token)
            user = User.objects.get(id=payload['user_id'])
            
            return (user, token)
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('Invalid token')
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('User not found')
    
    @staticmethod
    def generate_token(user, expires_in_days=7):
        """Generate a JWT token for a user."""
        payload = {
            'user_id': str(user.id),
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(days=expires_in_days),
            'iat': datetime.utcnow(),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    
    @staticmethod
    def decode_token(token):
        """Decode and validate a JWT token."""
        return jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])


def generate_auth_token(user):
    """Convenience function to generate auth token."""
    return TokenAuthentication.generate_token(user)
