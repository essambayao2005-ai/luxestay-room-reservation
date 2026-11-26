"""
Views for the staff/administrator dashboard module (/manage/).
Every view enforces staff permissions via @staff_required and delegates
approval/decline transitions to rooms/services.py.
"""

import csv
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, Count, Exists, OuterRef, ProtectedError, Q, Value, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.permissions import get_profile, staff_required
from rooms.models import Reservation, Room
from rooms.services import approve_reservation, decline_reservation

from .forms import ReportFilterForm, RoomForm

User = get_user_model()


def _annotate_conflicts(queryset):
    """Annotates pending reservations with `has_conflict=True` when an approved
    reservation for the same room and date overlaps them in time.
    Uses a single SQL Exists subquery (zero extra queries per row).
    Non-pending rows always get has_conflict=False.
    """
    overlap_approved = Reservation.objects.filter(
        room=OuterRef('room_id'),
        reservation_date=OuterRef('reservation_date'),
        status='approved',
        start_time__lt=OuterRef('end_time'),
        end_time__gt=OuterRef('start_time'),
    )
    return queryset.annotate(
        has_conflict=Case(
            When(status='pending', then=Exists(overlap_approved)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )


def _extract_error_message(exc):
    """Extracts a clean human-readable message from ValidationError or PermissionDenied."""
    if hasattr(exc, 'messages') and exc.messages:
        return ' '.join(str(m) for m in exc.messages)
    return str(exc)


def _safe_next_url(request, fallback='dashboard:reservation_list'):
    """Returns a safe internal redirect target from POST 'next', or the fallback."""
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback


@staff_required
def home(request):
    """Administrator dashboard home (/manage/).
    Shows four stat cards (with count-up), today's approved schedule,
    and the newest pending reservation requests with quick Approve/Decline actions.
    """
    today = timezone.localdate()

    pending_requests_count = Reservation.objects.filter(status='pending').count()
    approved_today_count = Reservation.objects.filter(
        status='approved',
        reservation_date=today,
    ).count()
    active_rooms_count = Room.objects.filter(is_active=True).count()
    registered_users_count = User.objects.count()

    todays_schedule = (
        Reservation.objects.filter(reservation_date=today, status='approved')
        .select_related('room', 'requester', 'requester__profile')
        .order_by('start_time', 'room__name')
    )

    newest_pending = _annotate_conflicts(
        Reservation.objects.filter(status='pending')
        .select_related('room', 'requester', 'requester__profile')
        .order_by('-created_at', '-id')
    )[:8]

    return render(request, 'dashboard/home.html', {
        'page_title': 'Admin Dashboard',
        'stat_pending': pending_requests_count,
        'stat_approved_today': approved_today_count,
        'stat_active_rooms': active_rooms_count,
        'stat_registered_users': registered_users_count,
        'todays_schedule': todays_schedule,
        'newest_pending': newest_pending,
        'today': today,
    })


@staff_required
def reservation_list(request):
    """Manage reservations with Pending, Approved, and History tabs, search,
    efficient conflict detection, and 10-per-page pagination.
    """
    tab = request.GET.get('tab', 'pending').strip().lower()
    if tab not in ('pending', 'approved', 'history'):
        tab = 'pending'

    query = request.GET.get('q', '').strip()

    qs = Reservation.objects.select_related(
        'room', 'requester', 'requester__profile', 'processed_by'
    )

    if tab == 'pending':
        qs = qs.filter(status='pending').order_by('reservation_date', 'start_time', '-created_at')
    elif tab == 'approved':
        qs = qs.filter(status='approved').order_by('-reservation_date', '-start_time')
    else:
        qs = qs.order_by('-created_at', '-id')

    if query:
        qs = qs.filter(
            Q(requester__username__icontains=query)
            | Q(requester__first_name__icontains=query)
            | Q(requester__last_name__icontains=query)
            | Q(room__name__icontains=query)
            | Q(room__building__icontains=query)
            | Q(purpose__icontains=query)
        )

    qs = _annotate_conflicts(qs)

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'dashboard/reservation_list.html', {
        'page_title': 'Manage Reservations',
        'tab': tab,
        'query': query,
        'page_obj': page_obj,
        'reservations': page_obj.object_list,
    })


@staff_required
@require_POST
def reservation_approve(request, pk):
    """Approve a pending reservation via POST using rooms/services.py."""
    reservation = get_object_or_404(
        Reservation.objects.select_related('room', 'requester'),
        pk=pk,
    )
    try:
        approve_reservation(reservation, request.user)
        messages.success(
            request,
            f"Approved reservation for {reservation.room.name} on {reservation.reservation_date}.",
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, _extract_error_message(exc))

    return redirect(_safe_next_url(request))


@staff_required
@require_POST
def reservation_decline(request, pk):
    """Decline a pending reservation with required remarks via POST using rooms/services.py."""
    reservation = get_object_or_404(
        Reservation.objects.select_related('room', 'requester'),
        pk=pk,
    )
    remarks = request.POST.get('admin_remarks', '')
    try:
        decline_reservation(reservation, request.user, remarks)
        messages.success(
            request,
            f"Declined reservation for {reservation.room.name} on {reservation.reservation_date}.",
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, _extract_error_message(exc))

    return redirect(_safe_next_url(request))



# ---------------------------------------------------------------------------
# Room Management (FR-07)
# ---------------------------------------------------------------------------

@staff_required
def room_list(request):
    """List all campus rooms (active and inactive) with search, building, and status filters."""
    query = request.GET.get('q', '').strip()
    building = request.GET.get('building', '').strip()
    active_filter = request.GET.get('active', '').strip().lower()

    qs = Room.objects.annotate(reservation_count=Count('reservations')).order_by('building', 'name')

    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(building__icontains=query))
    if building:
        qs = qs.filter(building=building)
    if active_filter == 'active':
        qs = qs.filter(is_active=True)
    elif active_filter == 'inactive':
        qs = qs.filter(is_active=False)
    else:
        active_filter = ''

    buildings = list(
        Room.objects.exclude(building='')
        .values_list('building', flat=True)
        .distinct()
        .order_by('building')
    )

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'dashboard/room_list.html', {
        'page_title': 'Manage Rooms',
        'query': query,
        'selected_building': building,
        'active_filter': active_filter,
        'buildings': buildings,
        'page_obj': page_obj,
        'rooms': page_obj.object_list,
    })


@staff_required
def room_create(request):
    """Add a new campus room with optional validated photo upload."""
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES)
        if form.is_valid():
            room = form.save()
            messages.success(request, f"Room '{room.name}' has been added.")
            return redirect('dashboard:room_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = RoomForm()

    return render(request, 'dashboard/room_form.html', {
        'page_title': 'Add Room',
        'form': form,
        'is_edit': False,
    })


@staff_required
def room_edit(request, pk):
    """Edit an existing campus room and preview/replace its photo."""
    room = get_object_or_404(Room, pk=pk)

    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            room = form.save()
            messages.success(request, f"Room '{room.name}' has been updated.")
            return redirect('dashboard:room_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = RoomForm(instance=room)

    return render(request, 'dashboard/room_form.html', {
        'page_title': f'Edit Room — {room.name}',
        'form': form,
        'room': room,
        'is_edit': True,
    })


@staff_required
@require_POST
def room_toggle(request, pk):
    """Activate or deactivate a room via POST."""
    room = get_object_or_404(Room, pk=pk)
    room.is_active = not room.is_active
    room.save(update_fields=['is_active'])
    state_label = "activated" if room.is_active else "deactivated"
    messages.success(request, f"Room '{room.name}' has been {state_label}.")
    return redirect(_safe_next_url(request, fallback='dashboard:room_list'))


@staff_required
@require_POST
def room_delete(request, pk):
    """Delete a room only if it has no reservations (ProtectedError).
    Never deletes reservations; suggests deactivating instead.
    """
    room = get_object_or_404(Room, pk=pk)
    room_name = room.name
    try:
        room.delete()
        messages.success(request, f"Room '{room_name}' has been deleted.")
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete '{room_name}' because it has existing reservations. "
            "Deactivate the room instead so reservation history is preserved.",
        )
    return redirect(_safe_next_url(request, fallback='dashboard:room_list'))


# ---------------------------------------------------------------------------
# User Management (FR-07)
# ---------------------------------------------------------------------------

@staff_required
def user_list(request):
    """List registered users with search, user type, and active filters."""
    query = request.GET.get('q', '').strip()
    user_type = request.GET.get('user_type', '').strip()
    active_filter = request.GET.get('active', '').strip().lower()

    valid_user_types = {code for code, _ in Profile.USER_TYPES}

    qs = (
        User.objects.select_related('profile')
        .annotate(reservation_count=Count('reservations'))
        .order_by('-date_joined', 'username')
    )

    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    if user_type in valid_user_types:
        qs = qs.filter(profile__user_type=user_type)
    else:
        user_type = ''

    if active_filter == 'active':
        qs = qs.filter(is_active=True)
    elif active_filter == 'inactive':
        qs = qs.filter(is_active=False)
    else:
        active_filter = ''

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Safely attach profile using get_profile() so users without a Profile (e.g. admin1) never crash
    users = list(page_obj.object_list)
    for u in users:
        u.safe_profile = get_profile(u)

    return render(request, 'dashboard/user_list.html', {
        'page_title': 'Manage Users',
        'query': query,
        'user_type': user_type,
        'user_type_choices': Profile.USER_TYPES,
        'active_filter': active_filter,
        'page_obj': page_obj,
        'users': users,
    })


@staff_required
@require_POST
def user_toggle(request, pk):
    """Activate or deactivate a user via POST. Admins cannot deactivate themselves."""
    target_user = get_object_or_404(User, pk=pk)
    if target_user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect(_safe_next_url(request, fallback='dashboard:user_list'))

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])
    state_label = "activated" if target_user.is_active else "deactivated"
    messages.success(request, f"User '{target_user.username}' has been {state_label}.")
    return redirect(_safe_next_url(request, fallback='dashboard:user_list'))


@staff_required
@require_POST
def user_delete(request, pk):
    """Delete a user only if they have no reservations, are not the current admin,
    and are not a superuser.
    """
    target_user = get_object_or_404(User, pk=pk)
    if target_user.pk == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect(_safe_next_url(request, fallback='dashboard:user_list'))

    if target_user.is_superuser:
        messages.error(request, "Superuser accounts cannot be deleted from this page.")
        return redirect(_safe_next_url(request, fallback='dashboard:user_list'))

    username = target_user.username
    try:
        target_user.delete()
        messages.success(request, f"User '{username}' has been deleted.")
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete '{username}' because they have existing reservations. "
            "Deactivate the account instead so reservation history is preserved.",
        )
    return redirect(_safe_next_url(request, fallback='dashboard:user_list'))



# ---------------------------------------------------------------------------
# Reports & CSV Export (FR-09)
# ---------------------------------------------------------------------------

PRINT_ROW_CAP = 500


def _filter_report_reservations(request):
    """Shared filtering logic for both the HTML/print report and CSV export.
    Returns (form, queryset, filter_summary_list).
    """
    has_params = any(
        k in request.GET
        for k in ('date_from', 'date_to', 'room', 'requester', 'status')
    )
    form = ReportFilterForm(request.GET) if has_params else ReportFilterForm()

    qs = (
        Reservation.objects.select_related(
            'room', 'requester', 'requester__profile', 'processed_by'
        )
        .order_by('-reservation_date', '-start_time', '-id')
    )
    filter_parts = []

    if form.is_bound:
        if form.is_valid():
            date_from = form.cleaned_data.get('date_from')
            date_to = form.cleaned_data.get('date_to')
            room = form.cleaned_data.get('room')
            requester = (form.cleaned_data.get('requester') or '').strip()
            status = form.cleaned_data.get('status')

            if date_from:
                qs = qs.filter(reservation_date__gte=date_from)
                filter_parts.append(f"From: {date_from.isoformat()}")
            if date_to:
                qs = qs.filter(reservation_date__lte=date_to)
                filter_parts.append(f"To: {date_to.isoformat()}")
            if room:
                qs = qs.filter(room=room)
                filter_parts.append(f"Room: {room.name}")
            if requester:
                qs = qs.filter(
                    Q(requester__username__icontains=requester)
                    | Q(requester__first_name__icontains=requester)
                    | Q(requester__last_name__icontains=requester)
                )
                filter_parts.append(f"Requester: {requester}")
            if status:
                qs = qs.filter(status=status)
                filter_parts.append(f"Status: {dict(Reservation.STATUS_CHOICES).get(status, status)}")
        else:
            qs = qs.none()

    return form, qs, filter_parts


def _csv_safe(value):
    """Neutralize CSV formula injection (prefix cells starting with =, +, -, or @)."""
    text = '' if value is None else str(value)
    if text and text[0] in ('=', '+', '-', '@'):
        return "'" + text
    return text


@staff_required
def reports(request):
    """Reservation history report with filters, summary counts, 10/page screen
    pagination, and a print-ready full dataset (capped at 500 rows).
    """
    form, qs, filter_parts = _filter_report_reservations(request)

    if form.is_bound and not form.is_valid():
        messages.error(request, "Please correct the report filter errors.")

    summary = qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        approved=Count('id', filter=Q(status='approved')),
        declined=Count('id', filter=Q(status='declined')),
        cancelled=Count('id', filter=Q(status='cancelled')),
    )

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    screen_rows = list(page_obj.object_list)
    for r in screen_rows:
        r.safe_profile = get_profile(r.requester)

    print_rows = list(qs[:PRINT_ROW_CAP])
    for r in print_rows:
        r.safe_profile = get_profile(r.requester)
    print_capped = summary['total'] > PRINT_ROW_CAP

    # Preserve current filter query string (without page) for pagination & CSV export
    query_params = request.GET.copy()
    query_params.pop('page', None)
    filter_querystring = query_params.urlencode()

    return render(request, 'dashboard/reports.html', {
        'page_title': 'Reservation Reports',
        'form': form,
        'summary': summary,
        'page_obj': page_obj,
        'reservations': screen_rows,
        'print_rows': print_rows,
        'print_capped': print_capped,
        'print_row_cap': PRINT_ROW_CAP,
        'filter_parts': filter_parts,
        'filter_querystring': filter_querystring,
        'generated_at': timezone.localtime(),
    })


@staff_required
def reports_export(request):
    """Export the filtered reservation history to a CSV file."""
    form, qs, _ = _filter_report_reservations(request)

    if form.is_bound and not form.is_valid():
        messages.error(request, "Cannot export CSV: please fix the invalid date range.")
        return redirect('dashboard:reports')

    today_str = timezone.localdate().isoformat()
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="reservations_{today_str}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date',
        'Start Time',
        'End Time',
        'Room',
        'Building',
        'Requester',
        'Username',
        'User Type',
        'College / Department',
        'Purpose',
        'Attendees',
        'Status',
        'Admin Remarks',
        'Processed By',
    ])

    for res in qs.iterator(chunk_size=200):
        profile = get_profile(res.requester)
        user_type = profile.get_user_type_display() if profile else ''
        college = profile.college_department if profile else ''
        requester_name = res.requester.get_full_name() or res.requester.username
        processed_by = res.processed_by.username if res.processed_by else ''

        writer.writerow([
            _csv_safe(res.reservation_date.isoformat()),
            _csv_safe(res.start_time.strftime('%H:%M')),
            _csv_safe(res.end_time.strftime('%H:%M')),
            _csv_safe(res.room.name),
            _csv_safe(res.room.building),
            _csv_safe(requester_name),
            _csv_safe(res.requester.username),
            _csv_safe(user_type),
            _csv_safe(college),
            _csv_safe(res.purpose),
            _csv_safe(res.num_attendees),
            _csv_safe(res.get_status_display()),
            _csv_safe(res.admin_remarks),
            _csv_safe(processed_by),
        ])

    return response
