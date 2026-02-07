"""
Serializers for report endpoints.
"""

from rest_framework import serializers
from core.models import WeeklyReport, HygieneAlert


class WeeklyReportSerializer(serializers.ModelSerializer):
    """Weekly report serializer."""
    
    class Meta:
        model = WeeklyReport
        fields = [
            'id', 'start_date', 'end_date', 'total_tickets', 'total_commits',
            'tickets_completed', 'total_time_logged_seconds', 'unlinked_commits',
            'non_code_activities', 'summary_text', 'markdown_report',
            'report_data', 'created_at'
        ]


class WeeklyReportListSerializer(serializers.ModelSerializer):
    """Weekly report list serializer (without full data)."""
    
    class Meta:
        model = WeeklyReport
        fields = [
            'id', 'start_date', 'end_date', 'total_tickets', 'total_commits',
            'tickets_completed', 'total_time_logged_seconds', 'unlinked_commits',
            'non_code_activities', 'summary_text', 'created_at'
        ]


class HygieneAlertSerializer(serializers.ModelSerializer):
    """Hygiene alert serializer."""
    ticket_key = serializers.CharField(source='ticket.key', read_only=True, allow_null=True)
    commit_sha = serializers.SerializerMethodField()
    
    class Meta:
        model = HygieneAlert
        fields = [
            'id', 'alert_type', 'severity', 'title', 'description',
            'recommendation', 'ticket_key', 'commit_sha',
            'detected_for_start', 'detected_for_end',
            'is_resolved', 'resolved_at', 'created_at'
        ]
    
    def get_commit_sha(self, obj):
        return obj.commit.sha[:7] if obj.commit else None


class GenerateReportRequestSerializer(serializers.Serializer):
    """Request serializer for report generation."""
    since = serializers.DateTimeField()
    until = serializers.DateTimeField()
    sync_first = serializers.BooleanField(default=True)


class ResolveAlertSerializer(serializers.Serializer):
    """Request serializer for resolving alerts."""
    alert_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1
    )
