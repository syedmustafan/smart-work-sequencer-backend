"""
Report URL routes.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Reports
    path('generate/', views.GenerateReportView.as_view(), name='generate_report'),
    path('weekly/', views.WeeklyReportsListView.as_view(), name='weekly_reports'),
    path('weekly/create/', views.CreateWeeklyReportView.as_view(), name='create_weekly_report'),
    path('weekly/current/', views.CurrentWeekReportView.as_view(), name='current_week_report'),
    path('weekly/last/', views.LastWeekReportView.as_view(), name='last_week_report'),
    path('weekly/<uuid:pk>/', views.WeeklyReportDetailView.as_view(), name='weekly_report_detail'),
    
    # Analytics
    path('analytics/effort/', views.EffortAnalysisView.as_view(), name='effort_analysis'),
    
    # Hygiene
    path('hygiene/', views.HygieneAlertsView.as_view(), name='hygiene_alerts'),
    path('hygiene/summary/', views.HygieneSummaryView.as_view(), name='hygiene_summary'),
    path('hygiene/detect/', views.DetectHygieneIssuesView.as_view(), name='detect_hygiene'),
    path('hygiene/resolve/', views.ResolveAlertsView.as_view(), name='resolve_alerts'),
]
