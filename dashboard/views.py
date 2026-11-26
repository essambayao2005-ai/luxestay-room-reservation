"""
Views for the staff/administrator dashboard module (/manage/).
Every view enforces staff permissions via @staff_required and delegates
approval/decline transitions to rooms/services.py.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.permissions import staff_required
from rooms.models import Reservation, Room
from rooms.services import approve_reservation, decline_reservation

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
