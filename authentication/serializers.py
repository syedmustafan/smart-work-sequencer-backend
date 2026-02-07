"""
Serializers for authentication.
"""

from rest_framework import serializers
from core.models import User, OAuthToken


class UserSerializer(serializers.ModelSerializer):
    """User serializer."""
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'github_connected', 'jira_connected', 'created_at']
        read_only_fields = ['id', 'github_connected', 'jira_connected', 'created_at']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = ['email', 'username', 'password']
    
    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password']
        )
        return user


class OAuthTokenSerializer(serializers.ModelSerializer):
    """OAuth token serializer (no sensitive data exposed)."""
    
    class Meta:
        model = OAuthToken
        fields = ['id', 'provider', 'expires_at', 'scope', 'created_at', 'updated_at']
        read_only_fields = fields


class ConnectionStatusSerializer(serializers.Serializer):
    """Serializer for connection status response."""
    github = serializers.DictField()
    jira = serializers.DictField()
