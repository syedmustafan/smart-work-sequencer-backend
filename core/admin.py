from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, OAuthToken, Repository, JiraProject, 
    Ticket, Commit, TicketActivity, Worklog, 
    WeeklyReport, HygieneAlert
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['email', 'username', 'github_connected', 'jira_connected', 'created_at']
    list_filter = ['github_connected', 'jira_connected', 'is_active']
    search_fields = ['email', 'username']
    ordering = ['-created_at']


@admin.register(OAuthToken)
class OAuthTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'provider', 'expires_at', 'created_at']
    list_filter = ['provider']
    search_fields = ['user__email']


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'is_tracked', 'last_synced_at']
    list_filter = ['is_tracked', 'is_private']
    search_fields = ['full_name', 'user__email']


@admin.register(JiraProject)
class JiraProjectAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'user', 'is_tracked', 'last_synced_at']
    list_filter = ['is_tracked']
    search_fields = ['key', 'name', 'user__email']


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['key', 'title', 'status', 'user', 'created_at_jira']
    list_filter = ['status', 'issue_type']
    search_fields = ['key', 'title', 'user__email']


@admin.register(Commit)
class CommitAdmin(admin.ModelAdmin):
    list_display = ['sha_short', 'message_short', 'repository', 'is_unlinked', 'committed_at']
    list_filter = ['is_unlinked', 'repository']
    search_fields = ['sha', 'message', 'author_name']

    def sha_short(self, obj):
        return obj.sha[:7]
    sha_short.short_description = 'SHA'

    def message_short(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_short.short_description = 'Message'


@admin.register(TicketActivity)
class TicketActivityAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'activity_type', 'author', 'activity_at']
    list_filter = ['activity_type']
    search_fields = ['ticket__key', 'author']


@admin.register(Worklog)
class WorklogAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'time_spent_display', 'started_at']
    search_fields = ['ticket__key', 'author']


@admin.register(WeeklyReport)
class WeeklyReportAdmin(admin.ModelAdmin):
    list_display = ['user', 'start_date', 'end_date', 'total_tickets', 'total_commits', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email']


@admin.register(HygieneAlert)
class HygieneAlertAdmin(admin.ModelAdmin):
    list_display = ['alert_type', 'title', 'user', 'severity', 'is_resolved', 'created_at']
    list_filter = ['alert_type', 'severity', 'is_resolved']
    search_fields = ['title', 'user__email']
