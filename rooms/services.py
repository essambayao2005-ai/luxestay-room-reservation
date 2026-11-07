"""
Business actions and workflow operations for reservations.
Every function validates business rules server-side before persisting data.
"""

import datetime
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Reservation


def create_reservation(room, requester, reservation_date, start_time, end_time, purpose, num_attendees):
    """Builds and validates a new reservation request.
    Important: The `room` and `requester` are bound to the instance BEFORE validation
    so that `Reservation.clean()` can execute capacity and overlap checks properly.
    """
    reservation = Reservation(
        room=room,
        requester=requester,
        reservation_date=reservation_date,
        start_time=start_time,
        end_time=end_time,
        purpose=purpose,
        num_attendees=num_attendees,
        status='pending',
    )
    # Server-side validation via model clean()
    reservation.full_clean()
    reservation.save()
    return reservation


def update_pending_reservation(reservation, user, **fields):
    """Updates fields on an existing reservation.
    Only the owner can edit, and only while the status is still 'pending'.
    Re-validates through full_clean(), which enforces that pending reservations
    cannot be moved into past dates or made to overlap existing bookings.
    """
    if reservation.requester != user:
        raise PermissionDenied("You can only edit your own reservations.")

    if reservation.status != 'pending':
        raise ValidationError("Only pending reservations can be edited.")

    updatable_fields = {'reservation_date', 'start_time', 'end_time', 'purpose', 'num_attendees', 'room'}
    for key, value in fields.items():
        if key in updatable_fields:
            setattr(reservation, key, value)

    # Re-run full validation including the clean() rules
    reservation.full_clean()
    reservation.save()
    return reservation


def cancel_reservation(reservation, user):
    """Cancels a pending reservation by its owner.
    Transitions status to 'cancelled'. Approved or already declined records cannot be cancelled.
    """
    if reservation.requester != user:
        raise PermissionDenied("You can only cancel your own reservations.")

    if reservation.status != 'pending':
        raise ValidationError("Only pending reservations can be cancelled.")

    reservation.status = 'cancelled'
    reservation.save(update_fields=['status', 'updated_at'])
    return reservation


def approve_reservation(reservation, admin_user):
    """Approves a pending reservation within a database transaction.
    - Requires staff privileges (admin_user.is_staff).
    - Uses select_for_update() to prevent concurrent approval race conditions.
    - Refuses if the reservation's end date and time are already in the past.
    - Sets processed_by and status='approved'.
    - Re-runs overlap validation via full_clean() to catch conflicts.
    """
    if not (admin_user and admin_user.is_authenticated and admin_user.is_staff):
        raise PermissionDenied("Administrator privileges are required to approve reservations.")

    with transaction.atomic():
        res = (
            Reservation.objects.select_for_update()
            .select_related('room', 'requester')
            .get(pk=reservation.pk)
        )

        if res.status != 'pending':
            raise ValidationError("Only pending reservations can be approved.")

        # Check if the reservation's end date and time are already in the past
        now = timezone.localtime()
        tz = timezone.get_current_timezone()
        res_end_datetime = timezone.make_aware(
            datetime.datetime.combine(res.reservation_date, res.end_time), tz
        )

        if res_end_datetime <= now:
            raise ValidationError("Cannot approve a reservation whose date and time have already passed.")

        # Set status to approved and record approving admin
        res.status = 'approved'
        res.processed_by = admin_user

        # Re-check overlap with approved reservations (clean() checks overlapping_approved)
        res.full_clean()
        res.save()
        return res


def decline_reservation(reservation, admin_user, remarks):
    """Declines a pending reservation with required administrative remarks.
    - Requires staff privileges.
    - Remarks are mandatory and cannot be blank.
    - Sets status='declined' and records processed_by.
    """
    if not (admin_user and admin_user.is_authenticated and admin_user.is_staff):
        raise PermissionDenied("Administrator privileges are required to decline reservations.")

    cleaned_remarks = str(remarks).strip() if remarks else ''
    if not cleaned_remarks:
        raise ValidationError("Administrative remarks are required when declining a reservation.")

    with transaction.atomic():
        res = (
            Reservation.objects.select_for_update()
            .select_related('room', 'requester')
            .get(pk=reservation.pk)
        )

        if res.status != 'pending':
            raise ValidationError("Only pending reservations can be declined.")

        res.status = 'declined'
        res.admin_remarks = cleaned_remarks
        res.processed_by = admin_user
        res.save()
        return res
