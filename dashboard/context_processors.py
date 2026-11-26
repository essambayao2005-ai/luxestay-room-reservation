"""
Context processors for the dashboard app.
Exposes the pending reservation count to staff users for the sidebar badge.
"""

from rooms.models import Reservation


def pending_reservations_count(request):
    """Provide `pending_count` only when the authenticated user is staff.
    Visitors and regular requesters never receive this context variable.
    """
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and user.is_staff:
        return {
            'pending_count': Reservation.objects.filter(status='pending').count(),
        }
    return {}
