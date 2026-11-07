"""
Read-only queries and availability helpers for rooms and the Availability Board.
"""

from django.db.models import Exists, OuterRef, Value, BooleanField
from django.utils import timezone
import datetime

from .models import Room, Reservation


def get_buildings():
    """Returns a sorted list of distinct buildings of currently active rooms."""
    return list(
        Room.objects.filter(is_active=True)
        .exclude(building='')
        .values_list('building', flat=True)
        .distinct()
        .order_by('building')
    )


def rooms_with_status(date, start_time, end_time, building=None, min_capacity=None):
    """Returns active rooms, each annotated with an `is_occupied` boolean flag.
    A room is occupied (True) if an APPROVED reservation for that room overlaps
    the requested slot on that date:
        existing.start_time < end_time AND existing.end_time > start_time.
    Uses an SQL Exists subquery for optimal single-query performance (no Python loops).
    """
    qs = Room.objects.filter(is_active=True)

    if building:
        qs = qs.filter(building=building)

    if min_capacity is not None:
        qs = qs.filter(capacity__gte=min_capacity)

    if date and start_time and end_time:
        # Overlap condition: start_time < requested_end AND end_time > requested_start
        overlap_subquery = Reservation.objects.filter(
            room=OuterRef('pk'),
            reservation_date=date,
            status='approved',
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        qs = qs.annotate(is_occupied=Exists(overlap_subquery))
    else:
        qs = qs.annotate(is_occupied=Value(False, output_field=BooleanField()))

    return qs.order_by('building', 'name')


def day_schedule(date, building=None):
    """Fetches all approved reservations for a given date in a SINGLE database query,
    with related room and requester models joined via select_related.
    Returns a dictionary mapping Room instances to lists of approved Reservation instances,
    ready for server-side rendering on the Availability Board timetable.
    """
    reservations = (
        Reservation.objects.filter(reservation_date=date, status='approved')
        .select_related('room', 'requester', 'processed_by')
        .order_by('room__building', 'room__name', 'start_time')
    )

    if building:
        reservations = reservations.filter(room__building=building)

    grouped = {}
    for res in reservations:
        grouped.setdefault(res.room, []).append(res)

    return grouped


def current_status(room, now=None):
    """Returns 'Free now' or 'In use until H:MM AM/PM' computed from approved
    reservations of today.
    """
    if now is None:
        now = timezone.localtime()

    current_date = now.date()
    current_time = now.time()

    # Find any approved reservation covering the current moment
    active_reservation = (
        Reservation.objects.filter(
            room=room,
            reservation_date=current_date,
            status='approved',
            start_time__lte=current_time,
            end_time__gt=current_time,
        )
        .order_by('end_time')
        .first()
    )

    if active_reservation:
        # Format time like '3:00 PM' (strip leading zero if present)
        formatted_time = active_reservation.end_time.strftime('%I:%M %p')
        if formatted_time.startswith('0'):
            formatted_time = formatted_time[1:]
        return f"In use until {formatted_time}"

    return "Free now"

