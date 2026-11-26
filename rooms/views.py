"""
Views for the rooms app.
Provides the campus room directory, slot availability search,
and the interactive Availability Board timetable.
"""

import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import get_user_reservation_or_404
from .availability import current_status_map, get_board_data, get_buildings, rooms_with_status
from .forms import ReservationForm, RoomSearchForm
from .models import Reservation, Room
from .services import cancel_reservation, create_reservation, update_pending_reservation


def _get_room_initials(name):
    """Generates a clean 2-3 character initials abbreviation for the room card fallback."""
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    if parts and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    return "RM"


def _parse_date(date_str):
    """Safely parses a YYYY-MM-DD date string, defaulting to local today on failure."""
    if not date_str:
        return timezone.localdate()
    try:
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return timezone.localdate()


def room_list(request):
    """Public campus rooms directory and availability search view.
    Accessible to visitors, requesters, and staff alike.
    Displays room cards with live status (Free now / In use until...)
    and time slot availability indicators when searched.
    Also supports timetable board view via ?view=board.
    Never exposes requester names or private reservation purposes.
    """
    view_mode = request.GET.get('view', 'cards')
    is_slot_searched = False
    searched_date = None
    searched_start = None
    searched_end = None

    # Check if any search parameter was submitted in GET
    has_get_params = any(
        k in request.GET
        for k in ('date', 'start_time', 'end_time', 'building', 'min_capacity', 'available_only')
    )

    if has_get_params:
        form = RoomSearchForm(request.GET)
        if form.is_valid():
            date = form.cleaned_data.get('date')
            start_time = form.cleaned_data.get('start_time')
            end_time = form.cleaned_data.get('end_time')
            building = form.cleaned_data.get('building') or None
            min_capacity = form.cleaned_data.get('min_capacity')
            available_only = form.cleaned_data.get('available_only')

            if date and start_time and end_time:
                # Active time slot search: compute is_occupied via SQL Exists subquery
                is_slot_searched = True
                searched_date = date
                searched_start = start_time
                searched_end = end_time

                rooms = rooms_with_status(
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                    building=building,
                    min_capacity=min_capacity,
                )

                if available_only:
                    rooms = rooms.filter(is_occupied=False)

                # Prioritize available rooms first, then sort by building and name
                rooms = rooms.order_by('is_occupied', 'building', 'name')
            else:
                # Filter by building or capacity without slot occupancy check
                rooms = rooms_with_status(
                    date=None,
                    start_time=None,
                    end_time=None,
                    building=building,
                    min_capacity=min_capacity,
                ).order_by('building', 'name')
        else:
            # Form has validation errors: show active rooms without slot check
            rooms = rooms_with_status(None, None, None).order_by('building', 'name')
    else:
        # Initial visit: empty form, default date to today, list all active rooms
        form = RoomSearchForm()
        rooms = rooms_with_status(None, None, None).order_by('building', 'name')

    # Convert to list and compute live "Free now / In use until" status in ONE query
    room_items = list(rooms)
    status_map = current_status_map(room_items, now=timezone.localtime())

    for r in room_items:
        r.current_status_text = status_map.get(r.pk, "Free now")
        r.initials = _get_room_initials(r.name)

    context = {
        'page_title': 'Campus Rooms & Availability',
        'form': form,
        'rooms': room_items,
        'view_mode': view_mode,
        'is_slot_searched': is_slot_searched,
        'searched_date': searched_date,
        'searched_start': searched_start,
        'searched_end': searched_end,
    }

    # If board view requested on root URL, inject board timetable data
    if view_mode == 'board':
        date_param = request.GET.get('date')
        selected_date = _parse_date(date_param)
        building_param = request.GET.get('building') or None
        board_data = get_board_data(date=selected_date, building=building_param, user=request.user)
        today = timezone.localdate()
        prev_date = selected_date - datetime.timedelta(days=1)
        next_date = selected_date + datetime.timedelta(days=1)

        context.update({
            'selected_date': selected_date,
            'selected_date_str': selected_date.isoformat(),
            'prev_date_str': prev_date.isoformat(),
            'next_date_str': next_date.isoformat(),
            'today_str': today.isoformat(),
            'selected_building': building_param or '',
            'buildings': get_buildings(),
            'board': board_data,
        })

    return render(request, 'rooms/room_list.html', context)


def availability_board(request):
    """Public dedicated Availability Board timetable view (/board/).
    Renders rooms grouped by building with reservation blocks laid out on an hour grid (7 AM - 9 PM).
    Computes CSS variables in Python and enforces the privacy rule.
    """
    date_param = request.GET.get('date')
    selected_date = _parse_date(date_param)
    building_param = request.GET.get('building') or None

    board_data = get_board_data(date=selected_date, building=building_param, user=request.user)
    buildings = get_buildings()

    today = timezone.localdate()
    prev_date = selected_date - datetime.timedelta(days=1)
    next_date = selected_date + datetime.timedelta(days=1)

    context = {
        'page_title': 'Campus Availability Board',
        'selected_date': selected_date,
        'selected_date_str': selected_date.isoformat(),
        'prev_date_str': prev_date.isoformat(),
        'next_date_str': next_date.isoformat(),
        'today_str': today.isoformat(),
        'selected_building': building_param or '',
        'buildings': buildings,
        'board': board_data,
        'view_mode': 'board',
    }
    return render(request, 'rooms/availability_board.html', context)



def _parse_time(time_str):
    """Safely parses an HH:MM time string, returning None if invalid."""
    if not time_str:
        return None
    try:
        return datetime.time.fromisoformat(time_str)
    except (ValueError, TypeError):
        return None


def _flash_form_errors(request, form):
    """Surface form/model validation errors via Django messages."""
    if form.non_field_errors():
        for err in form.non_field_errors():
            messages.error(request, err)
    else:
        messages.error(request, "Please correct the highlighted errors below.")


@login_required
def reservation_create(request, room_id):
    """Create a new reservation request for an active room.
    Inactive or non-existent rooms return HTTP 404.
    Supports prefilling date and start_time from ?date= and ?start= query params
    (used by clickable cells on the Availability Board).
    """
    room = get_object_or_404(Room, pk=room_id, is_active=True)

    if request.method == 'POST':
        # Bind room and requester on the instance BEFORE validation so clean() runs
        # capacity and overlap checks properly.
        instance = Reservation(room=room, requester=request.user)
        form = ReservationForm(request.POST, instance=instance)
        if form.is_valid():
            try:
                create_reservation(
                    room=room,
                    requester=request.user,
                    reservation_date=form.cleaned_data['reservation_date'],
                    start_time=form.cleaned_data['start_time'],
                    end_time=form.cleaned_data['end_time'],
                    purpose=form.cleaned_data['purpose'],
                    num_attendees=form.cleaned_data['num_attendees'],
                )
                messages.success(
                    request,
                    f"Reservation request for {room.name} submitted and is pending approval.",
                )
                return redirect('rooms:my_reservations')
            except ValidationError as exc:
                form.add_error(None, exc)
                _flash_form_errors(request, form)
        else:
            _flash_form_errors(request, form)
    else:
        initial = {}
        date_param = request.GET.get('date')
        if date_param:
            try:
                initial['reservation_date'] = datetime.date.fromisoformat(date_param)
            except (ValueError, TypeError):
                pass
        start_param = _parse_time(request.GET.get('start'))
        if start_param:
            initial['start_time'] = start_param

        form = ReservationForm(
            instance=Reservation(room=room, requester=request.user),
            initial=initial,
        )

    return render(request, 'rooms/reservation_form.html', {
        'page_title': f'Reserve {room.name}',
        'room': room,
        'form': form,
        'is_edit': False,
    })


@login_required
def my_reservations(request):
    """Display the logged-in user's own reservations, newest first.
    Supports filtering by status, pagination (10 per page), and avoids N+1 queries
    with select_related.
    """
    status_filter = request.GET.get('status', '').strip()
    valid_statuses = {code for code, _ in Reservation.STATUS_CHOICES}

    qs = (
        Reservation.objects.filter(requester=request.user)
        .select_related('room', 'processed_by')
        .order_by('-created_at', '-id')
    )
    if status_filter in valid_statuses:
        qs = qs.filter(status=status_filter)
    else:
        status_filter = ''

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'rooms/my_reservations.html', {
        'page_title': 'My Reservations',
        'page_obj': page_obj,
        'reservations': page_obj.object_list,
        'status_filter': status_filter,
        'status_choices': Reservation.STATUS_CHOICES,
    })


@login_required
def reservation_edit(request, pk):
    """Edit an existing pending reservation owned by the logged-in user.
    Returns 404 if not found or owned by another user.
    Re-validates all rules (including past-date and overlap) via update_pending_reservation().
    """
    reservation = get_user_reservation_or_404(request.user, pk)

    if reservation.status != 'pending':
        messages.error(request, "Only pending reservations can be edited.")
        return redirect('rooms:my_reservations')

    if request.method == 'POST':
        form = ReservationForm(request.POST, instance=reservation)
        if form.is_valid():
            try:
                update_pending_reservation(
                    reservation,
                    request.user,
                    reservation_date=form.cleaned_data['reservation_date'],
                    start_time=form.cleaned_data['start_time'],
                    end_time=form.cleaned_data['end_time'],
                    purpose=form.cleaned_data['purpose'],
                    num_attendees=form.cleaned_data['num_attendees'],
                )
                messages.success(request, "Your reservation request has been updated.")
                return redirect('rooms:my_reservations')
            except ValidationError as exc:
                form.add_error(None, exc)
                _flash_form_errors(request, form)
        else:
            _flash_form_errors(request, form)
    else:
        form = ReservationForm(instance=reservation)

    return render(request, 'rooms/reservation_form.html', {
        'page_title': f'Edit Reservation — {reservation.room.name}',
        'room': reservation.room,
        'reservation': reservation,
        'form': form,
        'is_edit': True,
    })


@login_required
@require_POST
def reservation_cancel(request, pk):
    """Cancel a pending reservation owned by the logged-in user (POST only).
    Returns 404 if not found or owned by another user.
    """
    reservation = get_user_reservation_or_404(request.user, pk)
    try:
        cancel_reservation(reservation, request.user)
        messages.success(
            request,
            f"Reservation for {reservation.room.name} on {reservation.reservation_date} has been cancelled.",
        )
    except ValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
        messages.error(request, msg)
    return redirect('rooms:my_reservations')
