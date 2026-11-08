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


def current_status_map(rooms, now=None):
    """Returns a dictionary mapping room_id (int) to a status string:
    'Free now' or 'In use until H:MM AM/PM' for multiple rooms in a SINGLE database query.
    Avoids N+1 query overhead when displaying room lists.
    """
    if now is None:
        now = timezone.localtime()

    current_date = now.date()
    current_time = now.time()

    room_list = list(rooms)
    if not room_list:
        return {}

    room_ids = [r.pk if hasattr(r, 'pk') else r for r in room_list]

    # ONE single query fetching all approved reservations covering current_time today
    active_reservations = (
        Reservation.objects.filter(
            room_id__in=room_ids,
            reservation_date=current_date,
            status='approved',
            start_time__lte=current_time,
            end_time__gt=current_time,
        )
        .order_by('end_time')
    )

    # Map the earliest ending reservation to each room_id
    status_by_id = {}
    for res in active_reservations:
        if res.room_id not in status_by_id:
            formatted_time = res.end_time.strftime('%I:%M %p')
            if formatted_time.startswith('0'):
                formatted_time = formatted_time[1:]
            status_by_id[res.room_id] = f"In use until {formatted_time}"

    # Build result dict ensuring an entry for every room
    result = {}
    for r in room_list:
        pk = r.pk if hasattr(r, 'pk') else r
        result[pk] = status_by_id.get(pk, "Free now")

    return result


def get_board_data(date, building=None, user=None):
    """Prepares structured Availability Board timetable data for a given date.
    - Computes CSS grid start offsets and spans in Python for reservation blocks.
    - Queries reservations in ONE query using day_schedule().
    - Groups room rows by campus building.
    - Computes the 'now' line position if the date is today.
    - Strictly enforces the privacy rule:
      * Staff sees reservation purpose and requester's name.
      * The reservation owner sees their own purpose.
      * Visitors and other requesters see only 'Reserved' and the time.
    """
    from django.conf import settings

    start_hour = getattr(settings, 'BOARD_START_HOUR', 7)
    end_hour = getattr(settings, 'BOARD_END_HOUR', 21)
    total_hours = max(1, end_hour - start_hour)

    # 1. Generate hour headers
    hours = []
    for h in range(start_hour, end_hour):
        t_start = datetime.time(h, 0)
        t_end = datetime.time(h + 1, 0)
        lbl_start = t_start.strftime('%I %p').lstrip('0')
        lbl_end = t_end.strftime('%I %p').lstrip('0')
        hours.append({
            'hour': h,
            'col_index': h - start_hour + 1,
            'label': lbl_start,
            'time_24': t_start.strftime('%H:%M'),
            'time_range_label': f"{lbl_start} – {lbl_end}",
        })

    # 2. Fetch active rooms
    rooms_qs = Room.objects.filter(is_active=True)
    if building:
        rooms_qs = rooms_qs.filter(building=building)
    rooms = list(rooms_qs.order_by('building', 'name'))

    # 3. Fetch reservations for this date in ONE query
    reservations_by_room = day_schedule(date, building=building)

    # 4. Process privacy and block geometry for each room
    is_staff = bool(user and user.is_authenticated and user.is_staff)
    user_id = user.id if (user and user.is_authenticated) else None

    rooms_data = []
    for room in rooms:
        res_list = reservations_by_room.get(room, [])
        blocks = []
        for idx, res in enumerate(res_list):
            res_start = res.start_time.hour + res.start_time.minute / 60.0
            res_end = res.end_time.hour + res.end_time.minute / 60.0

            clamped_start = max(start_hour, min(end_hour, res_start))
            clamped_end = max(start_hour, min(end_hour, res_end))

            if clamped_end <= clamped_start:
                continue

            start_offset = clamped_start - start_hour
            span = clamped_end - clamped_start

            start_col = int(clamped_start - start_hour) + 1
            span_cols = max(1, int(round(clamped_end - clamped_start)))

            percent_left = (start_offset / total_hours) * 100.0
            percent_width = (span / total_hours) * 100.0

            t_start_fmt = res.start_time.strftime('%I:%M %p').lstrip('0')
            t_end_fmt = res.end_time.strftime('%I:%M %p').lstrip('0')
            time_str = f"{t_start_fmt} – {t_end_fmt}"

            # Privacy enforcement: never expose unauthorized names/purposes
            is_owner = bool(user_id and res.requester_id == user_id)
            if is_staff:
                full_name = res.requester.get_full_name()
                req_display = f"{full_name} ({res.requester.username})" if full_name else res.requester.username
                display_text = res.purpose
                sub_text = f"{req_display} • {time_str}"
                tooltip = f"{res.purpose} • {req_display} • {time_str}"
            elif is_owner:
                display_text = res.purpose
                sub_text = f"My Reservation ({time_str})"
                tooltip = f"{res.purpose} • {time_str}"
            else:
                display_text = "Reserved"
                sub_text = time_str
                tooltip = f"Reserved • {time_str}"

            blocks.append({
                'id': res.id,
                'start_col': start_col,
                'span_cols': span_cols,
                'percent_left': percent_left,
                'percent_width': percent_width,
                'css_style': f"--start: {start_col}; --span: {span_cols}; left: {percent_left:.2f}%; width: {percent_width:.2f}%;",
                'time_str': time_str,
                'display_text': display_text,
                'sub_text': sub_text,
                'tooltip': tooltip,
                'is_owner': is_owner,
                'block_index': idx,
            })

        rooms_data.append({
            'room': room,
            'blocks': blocks,
        })

    # 5. Group by building (preserving order)
    building_groups = {}
    for item in rooms_data:
        b_name = item['room'].building or 'Other Buildings'
        building_groups.setdefault(b_name, []).append(item)

    # 6. 'Now' line calculation (present whenever viewing today's timetable)
    now = timezone.localtime()
    is_today = (date == now.date())
    now_line = None
    if is_today:
        now_hour_float = now.hour + now.minute / 60.0
        clamped_now = max(start_hour, min(end_hour, now_hour_float))
        now_offset = clamped_now - start_hour
        now_percent = (now_offset / total_hours) * 100.0
        now_line = {
            'percent': now_percent,
            'time_label': now.strftime('%I:%M %p').lstrip('0'),
        }

    return {
        'hours': hours,
        'building_groups': building_groups,
        'has_rooms': bool(rooms),
        'is_today': is_today,
        'now_line': now_line,
        'start_hour': start_hour,
        'end_hour': end_hour,
        'total_hours': total_hours,
    }



