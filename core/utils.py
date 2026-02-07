"""
Utility functions for the application.
"""

import uuid
from core.models import User


def get_or_create_session_user(request):
    """Get or create a user based on session."""
    session_user_id = request.session.get('user_id')
    
    if session_user_id:
        try:
            return User.objects.get(id=session_user_id)
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
