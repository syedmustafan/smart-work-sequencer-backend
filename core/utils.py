"""
Utility functions for the application.
"""

import uuid
from core.models import User


def get_or_create_session_user(request):
    """
    Get or create a user based on session or X-User-ID header.
    Priority: X-User-ID header > session > create new
    """
    # Check for user ID in header (sent by frontend)
    user_id = request.headers.get('X-User-ID') or request.META.get('HTTP_X_USER_ID')
    
    # Also check query params for backwards compatibility
    if not user_id:
        user_id = request.query_params.get('user_id') if hasattr(request, 'query_params') else None
    
    # Check session
    if not user_id:
        user_id = request.session.get('user_id')
    
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            # Update session with this user
            request.session['user_id'] = str(user.id)
            return user
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
