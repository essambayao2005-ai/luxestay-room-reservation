"""
Views for the rooms app.
Provides the campus room directory and slot availability search.
"""

from django.shortcuts import render
from django.utils import timezone

from .availability import current_status_map, rooms_with_status
from .forms import RoomSearchForm


def _get_room_initials(name):
    """Generates a clean 2-3 character initials abbreviation for the room card fallback."""
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    if parts and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    return "RM"


def room_list(request):
    """Public campus rooms directory and availability search view.
    Accessible to visitors, requesters, and staff alike.
    Displays room cards with live status (Free now / In use until...)
    and time slot availability indicators when searched.
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
    return render(request, 'rooms/room_list.html', context)
