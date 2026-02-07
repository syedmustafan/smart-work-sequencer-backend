"""
Core models for Smart Work Sequencer.
"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended User model with additional fields."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    github_connected = models.BooleanField(default=False)
    jira_connected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email


class OAuthToken(models.Model):
    """Encrypted OAuth tokens for GitHub and Jira."""
    PROVIDER_CHOICES = [
        ('github', 'GitHub'),
        ('jira', 'Jira'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='oauth_tokens')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(null=True, blank=True)
    token_type = models.CharField(max_length=50, default='Bearer')
    expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.TextField(null=True, blank=True)
    cloud_id = models.CharField(max_length=100, null=True, blank=True)  # For Jira cloud ID
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'oauth_tokens'
        unique_together = ['user', 'provider']

    def __str__(self):
        return f"{self.user.email} - {self.provider}"


class Repository(models.Model):
    """GitHub repositories being tracked."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='repositories')
    github_id = models.BigIntegerField()
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=512)  # owner/repo
    description = models.TextField(null=True, blank=True)
    url = models.URLField()
    is_private = models.BooleanField(default=False)
    is_tracked = models.BooleanField(default=True)
    default_branch = models.CharField(max_length=100, default='main')
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'repositories'
        unique_together = ['user', 'github_id']

    def __str__(self):
        return self.full_name


class JiraProject(models.Model):
    """Jira projects being tracked."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='jira_projects')
    jira_id = models.CharField(max_length=100)
    key = models.CharField(max_length=50)  # Project key like "PROJ"
    name = models.CharField(max_length=255)
    cloud_id = models.CharField(max_length=100)
    is_tracked = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jira_projects'
        unique_together = ['user', 'jira_id', 'cloud_id']

    def __str__(self):
        return f"{self.key} - {self.name}"


class Ticket(models.Model):
    """Jira tickets/issues."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    project = models.ForeignKey(JiraProject, on_delete=models.CASCADE, related_name='tickets', null=True)
    jira_id = models.CharField(max_length=100)
    key = models.CharField(max_length=50)  # Ticket key like "PROJ-123"
    title = models.CharField(max_length=512)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=100)
    issue_type = models.CharField(max_length=100)
    priority = models.CharField(max_length=50, null=True, blank=True)
    assignee = models.CharField(max_length=255, null=True, blank=True)
    reporter = models.CharField(max_length=255, null=True, blank=True)
    url = models.URLField()
    created_at_jira = models.DateTimeField()
    updated_at_jira = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tickets'
        unique_together = ['user', 'jira_id']

    def __str__(self):
        return f"{self.key}: {self.title}"


class Commit(models.Model):
    """GitHub commits."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commits')
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='commits')
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='commits')
    sha = models.CharField(max_length=40)
    message = models.TextField()
    author_name = models.CharField(max_length=255)
    author_email = models.CharField(max_length=255)
    committed_at = models.DateTimeField()
    url = models.URLField()
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    files_changed = models.IntegerField(default=0)
    extracted_ticket_keys = models.JSONField(default=list)  # List of ticket keys found in message
    is_unlinked = models.BooleanField(default=False)  # True if no ticket found
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'commits'
        unique_together = ['user', 'repository', 'sha']
        ordering = ['-committed_at']

    def __str__(self):
        return f"{self.sha[:7]}: {self.message[:50]}"


class TicketActivity(models.Model):
    """Jira ticket activity (status changes, comments, etc.)."""
    ACTIVITY_TYPES = [
        ('status_change', 'Status Change'),
        ('comment', 'Comment'),
        ('field_change', 'Field Change'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ticket_activities')
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    author = models.CharField(max_length=255)
    
    # For status changes
    from_status = models.CharField(max_length=100, null=True, blank=True)
    to_status = models.CharField(max_length=100, null=True, blank=True)
    
    # For comments
    comment_body = models.TextField(null=True, blank=True)
    
    # For field changes
    field_name = models.CharField(max_length=100, null=True, blank=True)
    from_value = models.TextField(null=True, blank=True)
    to_value = models.TextField(null=True, blank=True)
    
    activity_at = models.DateTimeField()
    jira_id = models.CharField(max_length=100)  # Jira changelog/comment ID
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ticket_activities'
        ordering = ['-activity_at']

    def __str__(self):
        return f"{self.ticket.key} - {self.activity_type}"


class Worklog(models.Model):
    """Jira time tracking worklogs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='worklogs')
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='worklogs')
    jira_id = models.CharField(max_length=100)
    author = models.CharField(max_length=255)
    time_spent_seconds = models.IntegerField()
    time_spent_display = models.CharField(max_length=50)  # e.g., "2h 30m"
    comment = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'worklogs'
        unique_together = ['user', 'jira_id']
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.ticket.key} - {self.time_spent_display}"


class WeeklyReport(models.Model):
    """Generated weekly reports."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='weekly_reports')
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Summary stats
    total_tickets = models.IntegerField(default=0)
    total_commits = models.IntegerField(default=0)
    tickets_completed = models.IntegerField(default=0)
    total_time_logged_seconds = models.IntegerField(default=0)
    unlinked_commits = models.IntegerField(default=0)
    non_code_activities = models.IntegerField(default=0)
    
    # AI generated content
    summary_text = models.TextField()
    markdown_report = models.TextField()
    
    # Data snapshot
    report_data = models.JSONField()  # Full report data
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'weekly_reports'
        unique_together = ['user', 'start_date', 'end_date']
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.user.email} - {self.start_date} to {self.end_date}"


class HygieneAlert(models.Model):
    """Hygiene issues detected."""
    ALERT_TYPES = [
        ('commit_no_ticket', 'Commit without Jira ticket'),
        ('status_no_commit', 'Status change without commits'),
        ('time_no_code', 'Time logged without code'),
        ('stalled_ticket', 'Ticket worked on but never moved'),
        ('high_effort_low_output', 'High effort, low output'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hygiene_alerts')
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, default='warning')  # info, warning, critical
    title = models.CharField(max_length=255)
    description = models.TextField()
    recommendation = models.TextField()
    
    # Related objects
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True)
    commit = models.ForeignKey(Commit, on_delete=models.CASCADE, null=True, blank=True)
    
    # Date range when detected
    detected_for_start = models.DateField()
    detected_for_end = models.DateField()
    
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hygiene_alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.alert_type}: {self.title}"
