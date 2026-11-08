"""
Comprehensive unit and integration tests for rooms, availability, and services.
Tests run against an isolated test database without relying on real production/seed data.
"""

import datetime
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase, RequestFactory
from django.utils import timezone

from accounts.models import Profile
from accounts.permissions import staff_required, get_user_reservation_or_404, get_profile
from rooms.availability import get_buildings, rooms_with_status, day_schedule, current_status
from rooms.models import Room, Reservation
from rooms.services import (
    create_reservation,
    update_pending_reservation,
    cancel_reservation,
    approve_reservation,
    decline_reservation,
)


class RoomBackendFoundationTests(TestCase):
    def setUp(self):
        # Create users
        self.staff_user = User.objects.create_user(
            username='staff_tester',
            email='staff@msu.edu.ph',
            password='TestPassword123!',
            is_staff=True,
        )
        self.student_user = User.objects.create_user(
            username='student_tester',
            email='student@msu.edu.ph',
            password='TestPassword123!',
            is_staff=False,
        )
        self.other_user = User.objects.create_user(
            username='other_tester',
            email='other@msu.edu.ph',
            password='TestPassword123!',
            is_staff=False,
        )

        # Profiles
        Profile.objects.create(
            user=self.student_user,
            user_type='student',
            college_department='Computer Science',
            contact_number='09111111111',
        )

        # Rooms
        self.lab_room = Room.objects.create(
            name='Lab 101',
            building='IT Building',
            room_type='laboratory',
            capacity=40,
            is_active=True,
        )
        self.lecture_room = Room.objects.create(
            name='Lecture 201',
            building='CS Building',
            room_type='lecture',
            capacity=50,
            is_active=True,
        )
        self.inactive_room = Room.objects.create(
            name='Old Room',
            building='Storage Building',
            room_type='lecture',
            capacity=20,
            is_active=False,
        )

        # Reference dates
        self.today = timezone.localdate()
        self.tomorrow = self.today + datetime.timedelta(days=1)
        self.yesterday = self.today - datetime.timedelta(days=1)

    def test_overlap_is_blocked(self):
        """Creating a reservation that overlaps an approved reservation must raise ValidationError."""
        # 1. Existing approved reservation: 10:00 - 12:00
        create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Approved Session',
            num_attendees=25,
        )
        # Approve it
        res_approved = Reservation.objects.get(purpose='Approved Session')
        approve_reservation(res_approved, self.staff_user)

        # 2. Attempt to create overlapping reservation: 11:00 - 13:00 (overlaps 11:00-12:00)
        with self.assertRaises(ValidationError):
            create_reservation(
                room=self.lab_room,
                requester=self.other_user,
                reservation_date=self.tomorrow,
                start_time=datetime.time(11, 0),
                end_time=datetime.time(13, 0),
                purpose='Overlapping Attempt',
                num_attendees=20,
            )

    def test_back_to_back_is_allowed(self):
        """Back-to-back bookings (one ends exactly when next starts) must be allowed."""
        # Baseline approved: 10:00 - 12:00
        res1 = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Base Block',
            num_attendees=20,
        )
        approve_reservation(res1, self.staff_user)

        # Preceding back-to-back: 08:00 - 10:00 (ends when base starts)
        res_before = create_reservation(
            room=self.lab_room,
            requester=self.other_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(8, 0),
            end_time=datetime.time(10, 0),
            purpose='Before Block',
            num_attendees=20,
        )
        self.assertIsNotNone(res_before.pk)

        # Following back-to-back: 12:00 - 14:00 (starts when base ends)
        res_after = create_reservation(
            room=self.lab_room,
            requester=self.other_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(12, 0),
            end_time=datetime.time(14, 0),
            purpose='After Block',
            num_attendees=20,
        )
        self.assertIsNotNone(res_after.pk)

    def test_end_time_before_start_time_refused(self):
        """End time equal to or earlier than start time must be rejected."""
        with self.assertRaises(ValidationError):
            create_reservation(
                room=self.lab_room,
                requester=self.student_user,
                reservation_date=self.tomorrow,
                start_time=datetime.time(14, 0),
                end_time=datetime.time(13, 0),
                purpose='Invalid Times',
                num_attendees=20,
            )

        with self.assertRaises(ValidationError):
            create_reservation(
                room=self.lab_room,
                requester=self.student_user,
                reservation_date=self.tomorrow,
                start_time=datetime.time(14, 0),
                end_time=datetime.time(14, 0),
                purpose='Same Time',
                num_attendees=20,
            )

    def test_past_date_refused_on_create_and_edit(self):
        """Submitting or editing a reservation with a date in the past must be rejected."""
        # On create
        with self.assertRaises(ValidationError):
            create_reservation(
                room=self.lab_room,
                requester=self.student_user,
                reservation_date=self.yesterday,
                start_time=datetime.time(10, 0),
                end_time=datetime.time(12, 0),
                purpose='Past Reservation',
                num_attendees=20,
            )

        # On update of pending reservation
        pending_res = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Valid Tomorrow',
            num_attendees=20,
        )

        with self.assertRaises(ValidationError):
            update_pending_reservation(
                pending_res,
                self.student_user,
                reservation_date=self.yesterday,
            )

    def test_attendees_above_capacity_refused(self):
        """Number of attendees exceeding room capacity must be rejected."""
        # Lab capacity is 40; attempt 41
        with self.assertRaises(ValidationError):
            create_reservation(
                room=self.lab_room,
                requester=self.student_user,
                reservation_date=self.tomorrow,
                start_time=datetime.time(10, 0),
                end_time=datetime.time(12, 0),
                purpose='Over Capacity Event',
                num_attendees=41,
            )

    def test_approve_refuses_conflict(self):
        """Approving a pending request that conflicts with an already-approved booking must be refused."""
        # 1. Approved reservation: 10:00 - 12:00
        res_approved = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='First Approved',
            num_attendees=20,
        )
        approve_reservation(res_approved, self.staff_user)

        # 2. Conflicting pending reservation created bypassing clean() (e.g. submitted concurrently)
        res_conflict = Reservation.objects.create(
            room=self.lab_room,
            requester=self.other_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(13, 0),
            purpose='Conflicting Pending',
            num_attendees=20,
            status='pending',
        )

        with self.assertRaises(ValidationError):
            approve_reservation(res_conflict, self.staff_user)

    def test_approve_refuses_past_reservation(self):
        """Approving a reservation whose scheduled end time is in the past must be refused."""
        # Create a pending reservation in the past bypassing clean()
        past_res = Reservation.objects.create(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.yesterday,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Past Unapproved Event',
            num_attendees=20,
            status='pending',
        )

        with self.assertRaises(ValidationError):
            approve_reservation(past_res, self.staff_user)

    def test_decline_needs_remarks(self):
        """Declining a reservation requires non-empty admin remarks."""
        pending_res = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='To be declined',
            num_attendees=20,
        )

        # Empty remarks rejected
        with self.assertRaises(ValidationError):
            decline_reservation(pending_res, self.staff_user, remarks='')

        with self.assertRaises(ValidationError):
            decline_reservation(pending_res, self.staff_user, remarks='   ')

        # Valid remarks accepted
        declined_res = decline_reservation(
            pending_res, self.staff_user, remarks='Lab is reserved for scheduled maintenance.'
        )
        self.assertEqual(declined_res.status, 'declined')
        self.assertEqual(declined_res.admin_remarks, 'Lab is reserved for scheduled maintenance.')
        self.assertEqual(declined_res.processed_by, self.staff_user)

    def test_non_owner_cannot_cancel_or_update(self):
        """Users cannot edit or cancel reservations belonging to other users."""
        pending_res = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Student Session',
            num_attendees=20,
        )

        # Other user cannot cancel
        with self.assertRaises(PermissionDenied):
            cancel_reservation(pending_res, self.other_user)

        # Other user cannot update
        with self.assertRaises(PermissionDenied):
            update_pending_reservation(pending_res, self.other_user, purpose='Hacked Purpose')

        # Owner can cancel
        cancelled_res = cancel_reservation(pending_res, self.student_user)
        self.assertEqual(cancelled_res.status, 'cancelled')

    def test_user_without_profile_does_not_crash_get_profile(self):
        """get_profile() must return None gracefully when a user has no Profile."""
        # staff_user was created without a Profile
        profile = get_profile(self.staff_user)
        self.assertIsNone(profile)

        # student_user has a Profile
        student_profile = get_profile(self.student_user)
        self.assertIsNotNone(student_profile)
        self.assertEqual(student_profile.user_type, 'student')

        # Anonymous/None user handling
        self.assertIsNone(get_profile(None))

    def test_rooms_with_status_marks_occupied(self):
        """rooms_with_status() must mark rooms as occupied only if an approved reservation overlaps."""
        # Approve slot on Lab 101 tomorrow: 10:00 - 12:00
        res = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Occupied Test',
            num_attendees=20,
        )
        approve_reservation(res, self.staff_user)

        # Query overlapping slot: 11:00 - 13:00 tomorrow
        rooms = list(
            rooms_with_status(
                date=self.tomorrow,
                start_time=datetime.time(11, 0),
                end_time=datetime.time(13, 0),
            )
        )

        lab_result = next(r for r in rooms if r.name == 'Lab 101')
        lecture_result = next(r for r in rooms if r.name == 'Lecture 201')

        self.assertTrue(lab_result.is_occupied)
        self.assertFalse(lecture_result.is_occupied)
        # Inactive rooms must never be listed
        self.assertFalse(any(r.name == 'Old Room' for r in rooms))

    def test_day_schedule_uses_one_query(self):
        """day_schedule() must fetch and group all approved reservations for a date in exactly 1 query."""
        # Seed 3 approved reservations across rooms
        for i, room in enumerate([self.lab_room, self.lecture_room]):
            res = create_reservation(
                room=room,
                requester=self.student_user,
                reservation_date=self.tomorrow,
                start_time=datetime.time(8 + i * 2, 0),
                end_time=datetime.time(10 + i * 2, 0),
                purpose=f'Schedule Block {i}',
                num_attendees=20,
            )
            approve_reservation(res, self.staff_user)

        # Measure query count
        with self.assertNumQueries(1):
            schedule = day_schedule(self.tomorrow)

        self.assertIn(self.lab_room, schedule)
        self.assertIn(self.lecture_room, schedule)

    def test_current_status(self):
        """current_status() correctly returns 'Free now' or 'In use until H:MM AM/PM'."""
        now = timezone.localtime()
        current_time = now.time()

        # Initial status: Free now
        self.assertEqual(current_status(self.lab_room, now=now), "Free now")

        # Create active approved reservation spanning current time
        # E.g. start at now - 10 min, end at now + 50 min
        start = (now - datetime.timedelta(minutes=10)).time()
        end = (now + datetime.timedelta(minutes=50)).time()

        # Use objects.create to bypass clean() date/time restrictions for exact mock
        Reservation.objects.create(
            room=self.lab_room,
            requester=self.student_user,
            processed_by=self.staff_user,
            reservation_date=now.date(),
            start_time=start,
            end_time=end,
            purpose='Current In Use Event',
            num_attendees=20,
            status='approved',
        )

        status_str = current_status(self.lab_room, now=now)
        self.assertTrue(status_str.startswith("In use until"))

    def test_get_user_reservation_or_404(self):
        """get_user_reservation_or_404() returns reservation only to its owner and raises 404 otherwise."""
        res = create_reservation(
            room=self.lab_room,
            requester=self.student_user,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Owner Check',
            num_attendees=20,
        )

        # Owner gets it
        found = get_user_reservation_or_404(self.student_user, res.pk)
        self.assertEqual(found.pk, res.pk)

        # Non-owner raises Http404 (not 403)
        with self.assertRaises(Http404):
            get_user_reservation_or_404(self.other_user, res.pk)

        # Non-existent ID raises Http404
        with self.assertRaises(Http404):
            get_user_reservation_or_404(self.student_user, 999999)

    def test_staff_required_decorator(self):
        """staff_required view decorator redirects anonymous and blocks non-staff with 403."""
        factory = RequestFactory()

        @staff_required
        def dummy_admin_view(request):
            return "Staff Access Granted"

        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.messages.middleware import MessageMiddleware

        def apply_middleware(req):
            SessionMiddleware(lambda r: None).process_request(req)
            MessageMiddleware(lambda r: None).process_request(req)

        # 1. Unauthenticated request -> redirects to login
        req_anon = factory.get('/manage/')
        from django.contrib.auth.models import AnonymousUser
        req_anon.user = AnonymousUser()
        resp = dummy_admin_view(req_anon)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

        # 2. Authenticated non-staff -> raises PermissionDenied (403)
        req_student = factory.get('/manage/')
        req_student.user = self.student_user
        apply_middleware(req_student)
        with self.assertRaises(PermissionDenied):
            dummy_admin_view(req_student)

        # 3. Authenticated staff -> succeeds
        req_staff = factory.get('/manage/')
        req_staff.user = self.staff_user
        apply_middleware(req_staff)
        result = dummy_admin_view(req_staff)
        self.assertEqual(result, "Staff Access Granted")

    def test_get_buildings(self):
        """get_buildings() returns distinct buildings of active rooms."""
        buildings = get_buildings()
        self.assertIn('CS Building', buildings)
        self.assertIn('IT Building', buildings)
        self.assertNotIn('Storage Building', buildings)  # inactive


# ---------------------------------------------------------------------------
# Template rendering tests (Phase 3A) — sidebar and topbar partials
# ---------------------------------------------------------------------------

class SidebarTopbarRenderTests(TestCase):
    """
    Verify that partials/sidebar.html and partials/topbar.html render without
    raising any exception for the three user roles: anonymous visitor, a normal
    authenticated user (requester), and a staff/administrator user.

    Uses RequestFactory to build a fake GET request and Django's
    render_to_string() to exercise the full template engine path.
    """

    def setUp(self):
        self.factory = RequestFactory()

        # Staff user (admin-style, no Profile needed)
        self.staff_user = User.objects.create_user(
            username='sidebar_staff', password='pass', is_staff=True
        )

        # Normal authenticated user WITH a Profile
        self.requester = User.objects.create_user(
            username='sidebar_requester', password='pass'
        )
        Profile.objects.create(
            user=self.requester,
            user_type='faculty',
            college_department='CCS',
            contact_number='09001234567',
        )

    def _make_request(self, user, path='/design-preview/'):
        """Build a minimal GET request with the given user attached."""
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.messages.storage.fallback import FallbackStorage

        request = self.factory.get(path)
        request.user = user if user is not None else AnonymousUser()
        # Attach session and message storage so {% csrf_token %} and messages work
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        return request

    def _render(self, template_name, request):
        """Render a template with request in context; return the HTML string."""
        from django.template.loader import render_to_string
        return render_to_string(template_name, request=request)

    # --- Anonymous visitor ---

    def test_sidebar_anonymous_no_error(self):
        """sidebar.html renders for an unauthenticated (visitor) user."""
        from django.contrib.auth.models import AnonymousUser
        req = self._make_request(AnonymousUser())
        html = self._render('partials/sidebar.html', req)
        self.assertIn('/accounts/login/', html)
        self.assertNotIn('NoReverseMatch', html)

    def test_topbar_anonymous_no_error(self):
        """topbar.html renders for an unauthenticated (visitor) user."""
        from django.contrib.auth.models import AnonymousUser
        req = self._make_request(AnonymousUser())
        html = self._render('partials/topbar.html', req)
        self.assertIn('topbar', html)

    # --- Authenticated requester ---

    def test_sidebar_requester_no_error(self):
        """sidebar.html renders for an authenticated non-staff user."""
        req = self._make_request(self.requester)
        html = self._render('partials/sidebar.html', req)
        self.assertIn('/my-reservations/', html)
        self.assertNotIn('NoReverseMatch', html)

    def test_topbar_requester_no_error(self):
        """topbar.html renders for an authenticated non-staff user."""
        req = self._make_request(self.requester)
        html = self._render('partials/topbar.html', req)
        self.assertIn('topbar', html)

    # --- Staff / administrator ---

    def test_sidebar_staff_no_error(self):
        """sidebar.html renders for a staff/administrator user."""
        req = self._make_request(self.staff_user)
        html = self._render('partials/sidebar.html', req)
        self.assertIn('/manage/', html)
        self.assertNotIn('NoReverseMatch', html)

    def test_topbar_staff_no_error(self):
        """topbar.html renders for a staff/administrator user."""
        req = self._make_request(self.staff_user)
        html = self._render('partials/topbar.html', req)
        self.assertIn('topbar', html)

    # --- Staff user WITHOUT a Profile (matches admin1 in production) ---

    def test_sidebar_staff_no_profile_no_error(self):
        """sidebar.html renders for a staff user who has no Profile row (e.g. admin1)."""
        staff_no_profile = User.objects.create_user(
            username='sidebar_staff_noprofile', password='pass', is_staff=True
        )
        req = self._make_request(staff_no_profile)
        html = self._render('partials/sidebar.html', req)
        self.assertIn('Administrator', html)
        self.assertNotIn('NoReverseMatch', html)
