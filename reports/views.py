"""
API views for reports and analytics.
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework import status, views, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import WeeklyReport, HygieneAlert
from .serializers import (
    WeeklyReportSerializer, WeeklyReportListSerializer,
    HygieneAlertSerializer, GenerateReportRequestSerializer,
    ResolveAlertSerializer
)
from .services import ReportService, AnalyticsService

logger = logging.getLogger(__name__)


class GenerateReportView(views.APIView):
    """Generate a work report for a date range."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = GenerateReportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = ReportService(request.user)
            report = service.generate_report(
                since=serializer.validated_data['since'],
                until=serializer.validated_data['until'],
                sync_first=serializer.validated_data.get('sync_first', True),
            )
            return Response(report)
        except Exception as e:
            logger.exception(f"Error generating report: {e}")
            return Response(
                {'error': 'Failed to generate report'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WeeklyReportsListView(generics.ListAPIView):
    """List all weekly reports."""
    permission_classes = [IsAuthenticated]
    serializer_class = WeeklyReportListSerializer
    
    def get_queryset(self):
        return WeeklyReport.objects.filter(user=self.request.user)


class WeeklyReportDetailView(generics.RetrieveAPIView):
    """Get detailed weekly report."""
    permission_classes = [IsAuthenticated]
    serializer_class = WeeklyReportSerializer
    
    def get_queryset(self):
        return WeeklyReport.objects.filter(user=self.request.user)


class CreateWeeklyReportView(views.APIView):
    """Create a weekly report for a specific week."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = GenerateReportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = ReportService(request.user)
            report = service.create_weekly_report(
                start_date=serializer.validated_data['since'],
                end_date=serializer.validated_data['until'],
            )
            return Response(
                WeeklyReportSerializer(report).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.exception(f"Error creating weekly report: {e}")
            return Response(
                {'error': 'Failed to create weekly report'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CurrentWeekReportView(views.APIView):
    """Get or generate report for the current week."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Calculate current week bounds (Monday to Sunday)
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        # Convert to datetime
        since = timezone.make_aware(datetime.combine(start_of_week, datetime.min.time()))
        until = timezone.make_aware(datetime.combine(end_of_week, datetime.max.time()))
        
        try:
            service = ReportService(request.user)
            report = service.generate_report(since, until, sync_first=False)
            return Response(report)
        except Exception as e:
            logger.exception(f"Error getting current week report: {e}")
            return Response(
                {'error': 'Failed to get current week report'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LastWeekReportView(views.APIView):
    """Get or generate report for last week."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Calculate last week bounds
        today = timezone.now().date()
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = start_of_last_week + timedelta(days=6)
        
        since = timezone.make_aware(datetime.combine(start_of_last_week, datetime.min.time()))
        until = timezone.make_aware(datetime.combine(end_of_last_week, datetime.max.time()))
        
        # Check if we have a stored report
        existing = WeeklyReport.objects.filter(
            user=request.user,
            start_date=start_of_last_week,
            end_date=end_of_last_week,
        ).first()
        
        if existing:
            return Response(existing.report_data)
        
        try:
            service = ReportService(request.user)
            report = service.generate_report(since, until, sync_first=False)
            return Response(report)
        except Exception as e:
            logger.exception(f"Error getting last week report: {e}")
            return Response(
                {'error': 'Failed to get last week report'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== Analytics Views ====================

class EffortAnalysisView(views.APIView):
    """Get effort vs output analysis for a date range."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        since = request.query_params.get('since')
        until = request.query_params.get('until')
        
        if not since or not until:
            return Response(
                {'error': 'since and until parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
            
            service = AnalyticsService(request.user)
            analysis = service.get_effort_analysis_summary(since_dt, until_dt)
            return Response(analysis)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error getting effort analysis: {e}")
            return Response(
                {'error': 'Failed to get effort analysis'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== Hygiene Views ====================

class HygieneAlertsView(generics.ListAPIView):
    """List hygiene alerts."""
    permission_classes = [IsAuthenticated]
    serializer_class = HygieneAlertSerializer
    
    def get_queryset(self):
        queryset = HygieneAlert.objects.filter(user=self.request.user)
        
        # Filter by resolved status
        resolved = self.request.query_params.get('resolved')
        if resolved is not None:
            queryset = queryset.filter(is_resolved=resolved.lower() == 'true')
        
        # Filter by type
        alert_type = self.request.query_params.get('type')
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)
        
        # Filter by severity
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)
        
        return queryset


class HygieneSummaryView(views.APIView):
    """Get hygiene summary for a date range."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        since = request.query_params.get('since')
        until = request.query_params.get('until')
        
        if not since or not until:
            return Response(
                {'error': 'since and until parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
            
            service = AnalyticsService(request.user)
            summary = service.get_hygiene_summary(since_dt, until_dt)
            return Response(summary)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error getting hygiene summary: {e}")
            return Response(
                {'error': 'Failed to get hygiene summary'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DetectHygieneIssuesView(views.APIView):
    """Detect hygiene issues for a date range."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = GenerateReportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = AnalyticsService(request.user)
            alerts = service.detect_hygiene_issues(
                since=serializer.validated_data['since'],
                until=serializer.validated_data['until'],
            )
            return Response({
                'message': f'Detected {len(alerts)} hygiene issues',
                'alerts': HygieneAlertSerializer(alerts, many=True).data
            })
        except Exception as e:
            logger.exception(f"Error detecting hygiene issues: {e}")
            return Response(
                {'error': 'Failed to detect hygiene issues'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResolveAlertsView(views.APIView):
    """Resolve multiple hygiene alerts."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = ResolveAlertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        alert_ids = serializer.validated_data['alert_ids']
        
        updated = HygieneAlert.objects.filter(
            user=request.user,
            id__in=alert_ids,
            is_resolved=False,
        ).update(
            is_resolved=True,
            resolved_at=timezone.now()
        )
        
        return Response({
            'message': f'Resolved {updated} alerts',
            'resolved_count': updated
        })
