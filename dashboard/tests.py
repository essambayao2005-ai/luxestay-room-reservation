"""
Tests for Phase 4C: Admin Dashboard, Reservation Management, Approve/Decline,
conflict detection, and staff-only pending badge context processor.
"""

import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from rooms.availability import rooms_with_status
from rooms.models import Reservation, Room

User = get_user_model()


class DashboardAccessAndWorkflowTests(TestCase):
    """Integration tests for /manage/ views, permissions, and reservation workflows."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin_tester', password='pass', is_staff=True
        )
        self.student = User.objects.create_user(
            username='student.demo',
            first_name='Student',
            last_name='Demo',
            password='pass',
        )
        Profile.objects.create(
            user=self.student,
            user_type='student',
            college_department='College of Engineering',
            contact_number='09123456789',
        )
        self.other = User.objects.create_user(
            username='faculty.demo',
            first_name='Faculty',
            last_name='Demo',
            password='pass',
        )

        self.room1 = Room.objects.create(
            name='Eng Rm 101',
            building='Engineering',
            room_type='lecture',
            capacity=40,
            is_active=True,
        )
        self.room2 = Room.objects.create(
            name='CS Lab 2',
            building='CCS',
            room_type='laboratory',
            capacity=30,
            is_active=True,
        )
        self.inactive_room = Room.objects.create(
            name='Archived Rm',
            building='Old',
            room_type='lecture',
            capacity=10,
            is_active=False,
        )

        self.today = timezone.localdate()
        self.tomorrow = self.today + datetime.timedelta(days=1)
        self.yesterday = self.today - datetime.timedelta(days=1)

        # Approved reservation today on room1: 10:00 - 12:00
        self.approved_today = Reservation.objects.create(
            room=self.room1,
            requester=self.other,
            processed_by=self.staff,
            reservation_date=self.today,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Approved Today Class',
            num_attendees=20,
            status='approved',
        )

        # Pending reservation tomorrow on room1: 14:00 - 16:00 (no conflict)
        self.pending_ok = Reservation.objects.create(
            room=self.room1,
            requester=self.student,
            reservation_date=self.tomorrow,
            start_time=datetime.time(14, 0),
            end_time=datetime.time(16, 0),
            purpose='Clean Pending Workshop',
            num_attendees=25,
            status='pending',
        )

        # Pending reservation today on room1: 11:00 - 13:00 (overlaps approved_today)
        self.pending_conflict = Reservation.objects.create(
            room=self.room1,
            requester=self.student,
            reservation_date=self.today,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(13, 0),
            purpose='Conflicting Pending Request',
            num_attendees=15,
            status='pending',
        )

        # Pending reservation in the past (created directly in DB)
        self.pending_past = Reservation.objects.create(
            room=self.room2,
            requester=self.student,
            reservation_date=self.yesterday,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0),
            purpose='Past Pending Request',
            num_attendees=10,
            status='pending',
        )

    def test_anonymous_redirected_and_non_staff_gets_403_on_all_dashboard_urls(self):
        """Every dashboard URL redirects anonymous users and returns 403 for non-staff."""
        urls = [
            ('GET', reverse('dashboard:home')),
            ('GET', reverse('dashboard:reservation_list')),
            ('POST', reverse('dashboard:approve', args=[self.pending_ok.pk])),
            ('POST', reverse('dashboard:decline', args=[self.pending_ok.pk])),
        ]

        # Anonymous -> redirect to login
        for method, url in urls:
            resp = self.client.get(url) if method == 'GET' else self.client.post(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/accounts/login/', resp['Location'])

        # Non-staff -> 403 Forbidden
        self.client.force_login(self.student)
        for method, url in urls:
            resp = self.client.get(url) if method == 'GET' else self.client.post(url)
            self.assertEqual(resp.status_code, 403)

    def test_stat_card_numbers_are_correct(self):
        """Dashboard home displays accurate counts for pending, approved today, active rooms, and users."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('dashboard:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['stat_pending'], 3)          # ok, conflict, past
        self.assertEqual(resp.context['stat_approved_today'], 1)   # approved_today
        self.assertEqual(resp.context['stat_active_rooms'], 2)     # room1, room2
        self.assertEqual(resp.context['stat_registered_users'], 3) # staff, student, other

    def test_tabs_show_right_statuses_and_search_filters(self):
        """Pending, Approved, and History tabs filter by status, and ?q= filters results."""
        self.client.force_login(self.staff)
        url = reverse('dashboard:reservation_list')

        # Pending tab
        resp_pending = self.client.get(url + '?tab=pending')
        self.assertEqual(resp_pending.status_code, 200)
        pending_ids = {r.pk for r in resp_pending.context['reservations']}
        self.assertEqual(pending_ids, {self.pending_ok.pk, self.pending_conflict.pk, self.pending_past.pk})

        # Approved tab
        resp_approved = self.client.get(url + '?tab=approved')
        approved_ids = {r.pk for r in resp_approved.context['reservations']}
        self.assertEqual(approved_ids, {self.approved_today.pk})

        # History tab (all)
        resp_history = self.client.get(url + '?tab=history')
        history_ids = {r.pk for r in resp_history.context['reservations']}
        self.assertEqual(
            history_ids,
            {self.approved_today.pk, self.pending_ok.pk, self.pending_conflict.pk, self.pending_past.pk},
        )

        # Search within pending tab
        resp_search = self.client.get(url + '?tab=pending&q=Workshop')
        search_ids = {r.pk for r in resp_search.context['reservations']}
        self.assertEqual(search_ids, {self.pending_ok.pk})

    def test_conflict_flag_appears_only_on_overlapping_pending_request(self):
        """has_conflict is True only for pending requests overlapping an approved booking."""
        self.client.force_login(self.staff)
        url = reverse('dashboard:reservation_list')

        resp = self.client.get(url + '?tab=history')
        by_id = {r.pk: r for r in resp.context['reservations']}

        self.assertTrue(by_id[self.pending_conflict.pk].has_conflict)
        self.assertFalse(by_id[self.pending_ok.pk].has_conflict)
        self.assertFalse(by_id[self.pending_past.pk].has_conflict)
        self.assertFalse(by_id[self.approved_today.pk].has_conflict)

    def test_approve_works_and_room_becomes_occupied(self):
        """Approving a valid pending request sets status='approved' and marks room occupied."""
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse('dashboard:approve', args=[self.pending_ok.pk]),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.pending_ok.refresh_from_db()
        self.assertEqual(self.pending_ok.status, 'approved')
        self.assertEqual(self.pending_ok.processed_by, self.staff)

        # Verify rooms_with_status marks room1 occupied for that slot
        rooms = list(
            rooms_with_status(
                date=self.tomorrow,
                start_time=datetime.time(14, 30),
                end_time=datetime.time(15, 30),
            )
        )
        room1_status = next(r for r in rooms if r.pk == self.room1.pk)
        self.assertTrue(room1_status.is_occupied)

    def test_approve_refused_on_conflict_and_past_reservation(self):
        """Approving a conflicting or past reservation is refused and leaves status pending."""
        self.client.force_login(self.staff)

        # Conflict
        resp_conflict = self.client.post(
            reverse('dashboard:approve', args=[self.pending_conflict.pk]),
            follow=True,
        )
        self.pending_conflict.refresh_from_db()
        self.assertEqual(self.pending_conflict.status, 'pending')
        self.assertIn('already reserved', resp_conflict.content.decode())

        # Past
        resp_past = self.client.post(
            reverse('dashboard:approve', args=[self.pending_past.pk]),
            follow=True,
        )
        self.pending_past.refresh_from_db()
        self.assertEqual(self.pending_past.status, 'pending')
        self.assertIn('already passed', resp_past.content.decode())

    def test_decline_without_remarks_refused_and_with_remarks_succeeds(self):
        """Declining requires non-empty remarks; valid remarks set status='declined'."""
        self.client.force_login(self.staff)
        decline_url = reverse('dashboard:decline', args=[self.pending_ok.pk])

        # Blank remarks -> refused
        resp_blank = self.client.post(decline_url, {'admin_remarks': '   '}, follow=True)
        self.pending_ok.refresh_from_db()
        self.assertEqual(self.pending_ok.status, 'pending')
        self.assertIn('remarks are required', resp_blank.content.decode())

        # Valid remarks -> declined
        self.client.post(decline_url, {'admin_remarks': 'Room reserved for exam.'})
        self.pending_ok.refresh_from_db()
        self.assertEqual(self.pending_ok.status, 'declined')
        self.assertEqual(self.pending_ok.admin_remarks, 'Room reserved for exam.')
        self.assertEqual(self.pending_ok.processed_by, self.staff)

    def test_get_on_approve_and_decline_refused(self):
        """GET requests to approve and decline endpoints return 405 Method Not Allowed."""
        self.client.force_login(self.staff)
        resp_approve = self.client.get(reverse('dashboard:approve', args=[self.pending_ok.pk]))
        self.assertEqual(resp_approve.status_code, 405)

        resp_decline = self.client.get(reverse('dashboard:decline', args=[self.pending_ok.pk]))
        self.assertEqual(resp_decline.status_code, 405)

    def test_pending_badge_only_provided_to_staff(self):
        """pending_count context variable and badge are provided to staff, not visitors/requesters."""
        # Anonymous visitor on '/'
        resp_anon = self.client.get('/')
        self.assertNotIn('pending_count', resp_anon.context)

        # Non-staff requester on '/'
        self.client.force_login(self.student)
        resp_student = self.client.get('/')
        self.assertNotIn('pending_count', resp_student.context)

        # Staff user on '/manage/'
        self.client.force_login(self.staff)
        resp_staff = self.client.get(reverse('dashboard:home'))
        self.assertEqual(resp_staff.context['pending_count'], 3)
        self.assertIn('sidebar-badge-count', resp_staff.content.decode())
