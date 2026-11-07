"""
Permissions and access control helpers for user roles, profiles, and reservation access.
"""

from functools import wraps
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404

from rooms.models import Reservation


def staff_required(view_func):
    """View decorator that enforces staff/administrator permissions.
    - If unauthenticated: redirects to the login URL.
    - If authenticated but not staff: raises PermissionDenied (HTTP 403) with a message.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='/accounts/login/')
        if not request.user.is_staff:
            messages.error(request, "Access denied. Administrator privileges are required.")
            raise PermissionDenied("Administrator privileges are required.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def get_user_reservation_or_404(user, pk):
    """Retrieves a reservation only if it belongs to the specified user.
    Raises Http404 (not 403) if not found or if owned by another user.
    This prevents unauthorized ID enumeration of other users' reservations.
    """
    try:
        return (
            Reservation.objects.select_related('room', 'requester')
            .get(pk=pk, requester=user)
        )
    except Reservation.DoesNotExist:
        raise Http404("Reservation not found.")


def get_profile(user):
    """Safely retrieves the Profile instance for a given user, or None if it does not exist.
    Never throws RelatedObjectDoesNotExist, safely handling superusers or staff
    created via createsuperuser or the Django admin without a Profile record.
    """
    if not user or not user.is_authenticated:
        return None
    try:
        return getattr(user, 'profile', None)
    except Exception:
        return None

