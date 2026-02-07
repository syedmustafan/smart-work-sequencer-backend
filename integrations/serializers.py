"""
Serializers for integration endpoints.
"""

from rest_framework import serializers
from core.models import Repository, JiraProject, Commit, Ticket


class RepositorySerializer(serializers.ModelSerializer):
    """Repository serializer."""
    
    class Meta:
        model = Repository
        fields = [
            'id', 'github_id', 'name', 'full_name', 'description',
            'url', 'is_private', 'is_tracked', 'default_branch',
            'last_synced_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'github_id', 'name', 'full_name', 'description',
            'url', 'is_private', 'default_branch', 'last_synced_at', 'created_at'
        ]


class JiraProjectSerializer(serializers.ModelSerializer):
    """Jira project serializer."""
    
    class Meta:
        model = JiraProject
        fields = [
            'id', 'jira_id', 'key', 'name', 'is_tracked',
            'last_synced_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'jira_id', 'key', 'name', 'last_synced_at', 'created_at'
        ]


class CommitSerializer(serializers.ModelSerializer):
    """Commit serializer."""
    repository_name = serializers.CharField(source='repository.full_name', read_only=True)
    ticket_key = serializers.CharField(source='ticket.key', read_only=True, allow_null=True)
    
    class Meta:
        model = Commit
        fields = [
            'id', 'sha', 'message', 'author_name', 'author_email',
            'committed_at', 'url', 'additions', 'deletions', 'files_changed',
            'extracted_ticket_keys', 'is_unlinked', 'repository_name', 'ticket_key'
        ]


class TicketSerializer(serializers.ModelSerializer):
    """Ticket serializer."""
    commits_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Ticket
        fields = [
            'id', 'jira_id', 'key', 'title', 'description', 'status',
            'issue_type', 'priority', 'assignee', 'reporter', 'url',
            'created_at_jira', 'updated_at_jira', 'commits_count'
        ]
    
    def get_commits_count(self, obj):
        return obj.commits.count()


class SyncRequestSerializer(serializers.Serializer):
    """Request serializer for sync operations."""
    since = serializers.DateTimeField()
    until = serializers.DateTimeField()
    repository_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True
    )
    project_keys = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )


class DateRangeSerializer(serializers.Serializer):
    """Date range serializer for reports."""
    since = serializers.DateTimeField()
    until = serializers.DateTimeField()
