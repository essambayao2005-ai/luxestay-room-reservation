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

        # Future conflict (uses tomorrow so test passes at any hour of the day)
        Reservation.objects.create(
            room=self.room2,
            requester=self.other,
            processed_by=self.staff,
            reservation_date=self.tomorrow,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose='Tomorrow Approved',
            num_attendees=10,
            status='approved',
        )
        future_conflict = Reservation.objects.create(
            room=self.room2,
            requester=self.student,
            reservation_date=self.tomorrow,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(13, 0),
            purpose='Tomorrow Conflicting Pending',
            num_attendees=10,
            status='pending',
        )
        resp_conflict = self.client.post(
            reverse('dashboard:approve', args=[future_conflict.pk]),
            follow=True,
        )
        future_conflict.refresh_from_db()
        self.assertEqual(future_conflict.status, 'pending')
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


# ---------------------------------------------------------------------------
# Phase 4D: Manage Rooms & Users Tests
# ---------------------------------------------------------------------------

class ManageRoomsAndUsersTests(TestCase):
    """Integration tests for /manage/rooms/ and /manage/users/ workflows."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin1_test', email='admin1@msu.edu.ph', password='pass'
        )
        self.staff = User.objects.create_user(
            username='staff_mgr', email='staff@msu.edu.ph', password='pass', is_staff=True
        )
        self.student = User.objects.create_user(
            username='student.mgr',
            email='stud@msu.edu.ph',
            password='Str0ngPassword!',
            first_name='Juan',
            last_name='Dela Cruz',
        )
        Profile.objects.create(
            user=self.student,
            user_type='student',
            college_department='CCS',
            contact_number='09123456789',
        )
        self.empty_user = User.objects.create_user(
            username='empty.user',
            email='empty@msu.edu.ph',
            password='pass',
        )

        self.room_with_res = Room.objects.create(
            name='Occupied Rm 101',
            building='IT Building',
            room_type='laboratory',
            capacity=35,
            is_active=True,
        )
        self.empty_room = Room.objects.create(
            name='Empty Rm 102',
            building='CS Building',
            room_type='lecture',
            capacity=25,
            is_active=True,
        )

        self.tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.reservation = Reservation.objects.create(
            room=self.room_with_res,
            requester=self.student,
            reservation_date=self.tomorrow,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0),
            purpose='Protect Test',
            num_attendees=15,
            status='pending',
        )

    def _make_png_bytes(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (10, 10), color=(100, 30, 43)).save(buf, format='PNG')
        return buf.getvalue()

    def test_non_staff_and_anonymous_blocked_on_all_room_and_user_urls(self):
        """Anonymous users redirect to login; non-staff receive 403 on all 4D URLs."""
        urls = [
            ('GET', reverse('dashboard:room_list')),
            ('GET', reverse('dashboard:room_create')),
            ('GET', reverse('dashboard:room_edit', args=[self.empty_room.pk])),
            ('POST', reverse('dashboard:room_toggle', args=[self.empty_room.pk])),
            ('POST', reverse('dashboard:room_delete', args=[self.empty_room.pk])),
            ('GET', reverse('dashboard:user_list')),
            ('POST', reverse('dashboard:user_toggle', args=[self.empty_user.pk])),
            ('POST', reverse('dashboard:user_delete', args=[self.empty_user.pk])),
        ]

        for method, url in urls:
            resp = self.client.get(url) if method == 'GET' else self.client.post(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/accounts/login/', resp['Location'])

        self.client.force_login(self.student)
        for method, url in urls:
            resp = self.client.get(url) if method == 'GET' else self.client.post(url)
            self.assertEqual(resp.status_code, 403)

    def test_room_image_upload_valid_and_invalid_rejected(self):
        """Valid PNG uploads; invalid file types and oversized (>2 MB) files are refused."""
        import tempfile
        import shutil
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        tmp_media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=tmp_media):
                self.client.force_login(self.staff)
                add_url = reverse('dashboard:room_create')

                # 1. Invalid extension/content type (real GIF bytes so ImageField passes, clean_image rejects)
                import io
                from PIL import Image
                gif_buf = io.BytesIO()
                Image.new('RGB', (10, 10)).save(gif_buf, format='GIF')
                bad_file = SimpleUploadedFile('anim.gif', gif_buf.getvalue(), content_type='image/gif')
                resp_bad = self.client.post(add_url, {
                    'name': 'Bad Img Room',
                    'building': 'Test Bldg',
                    'room_type': 'lecture',
                    'capacity': 20,
                    'image': bad_file,
                })
                self.assertEqual(resp_bad.status_code, 200)
                self.assertIn('Unsupported file extension', resp_bad.content.decode())
                self.assertFalse(Room.objects.filter(name='Bad Img Room').exists())

                # 2. Oversized (> 2 MB) valid PNG
                big_buf = io.BytesIO()
                Image.new('RGB', (10, 10)).save(big_buf, format='PNG')
                big_bytes = big_buf.getvalue() + (b'\x00' * (2 * 1024 * 1024 + 10))
                big_file = SimpleUploadedFile('huge.png', big_bytes, content_type='image/png')
                resp_big = self.client.post(add_url, {
                    'name': 'Huge Img Room',
                    'building': 'Test Bldg',
                    'room_type': 'lecture',
                    'capacity': 20,
                    'image': big_file,
                })
                self.assertEqual(resp_big.status_code, 200)
                self.assertIn('Maximum allowed size is 2 MB', resp_big.content.decode())
                self.assertFalse(Room.objects.filter(name='Huge Img Room').exists())

                # 3. Valid PNG
                good_file = SimpleUploadedFile('room.png', self._make_png_bytes(), content_type='image/png')
                resp_ok = self.client.post(add_url, {
                    'name': 'Photo Room 301',
                    'building': 'Test Bldg',
                    'room_type': 'conference',
                    'capacity': 15,
                    'image': good_file,
                })
                self.assertRedirects(resp_ok, reverse('dashboard:room_list'))
                created = Room.objects.get(name='Photo Room 301')
                self.assertTrue(bool(created.image))
        finally:
            shutil.rmtree(tmp_media, ignore_errors=True)

    def test_delete_room_with_reservations_refused_and_without_succeeds(self):
        """Deleting a room with reservations is refused; deleting an empty room succeeds."""
        self.client.force_login(self.staff)

        # Protected room
        resp_protected = self.client.post(
            reverse('dashboard:room_delete', args=[self.room_with_res.pk]),
            follow=True,
        )
        self.assertTrue(Room.objects.filter(pk=self.room_with_res.pk).exists())
        self.assertIn('existing reservations', resp_protected.content.decode())

        # Empty room
        resp_empty = self.client.post(
            reverse('dashboard:room_delete', args=[self.empty_room.pk]),
            follow=True,
        )
        self.assertFalse(Room.objects.filter(pk=self.empty_room.pk).exists())
        self.assertIn('has been deleted', resp_empty.content.decode())

    def test_toggle_room_hides_from_public_page(self):
        """Deactivating a room hides it from '/' and reactivating shows it again."""
        self.client.force_login(self.staff)
        toggle_url = reverse('dashboard:room_toggle', args=[self.empty_room.pk])

        # Deactivate
        self.client.post(toggle_url, follow=True)
        self.empty_room.refresh_from_db()
        self.assertFalse(self.empty_room.is_active)

        public_resp = self.client.get('/')
        self.assertNotIn(self.empty_room, public_resp.context['rooms'])

        # Reactivate
        self.client.post(toggle_url, follow=True)
        self.empty_room.refresh_from_db()
        self.assertTrue(self.empty_room.is_active)

        public_resp2 = self.client.get('/')
        self.assertIn(self.empty_room, public_resp2.context['rooms'])

    def test_admin_cannot_deactivate_or_delete_self(self):
        """An admin cannot deactivate or delete their own account."""
        self.client.force_login(self.staff)

        resp_toggle = self.client.post(
            reverse('dashboard:user_toggle', args=[self.staff.pk]),
            follow=True,
        )
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)
        self.assertIn('cannot deactivate your own', resp_toggle.content.decode())

        resp_delete = self.client.post(
            reverse('dashboard:user_delete', args=[self.staff.pk]),
            follow=True,
        )
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())
        self.assertIn('cannot delete your own', resp_delete.content.decode())

    def test_superuser_cannot_be_deleted(self):
        """Superuser accounts cannot be deleted from /manage/users/."""
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse('dashboard:user_delete', args=[self.superuser.pk]),
            follow=True,
        )
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())
        self.assertIn('Superuser accounts cannot be deleted', resp.content.decode())

    def test_delete_user_with_reservations_refused_and_without_succeeds(self):
        """Deleting a user with reservations is refused; deleting an empty user succeeds."""
        self.client.force_login(self.staff)

        resp_protected = self.client.post(
            reverse('dashboard:user_delete', args=[self.student.pk]),
            follow=True,
        )
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())
        self.assertIn('existing reservations', resp_protected.content.decode())

        resp_empty = self.client.post(
            reverse('dashboard:user_delete', args=[self.empty_user.pk]),
            follow=True,
        )
        self.assertFalse(User.objects.filter(pk=self.empty_user.pk).exists())
        self.assertIn('has been deleted', resp_empty.content.decode())

    def test_get_on_toggle_and_delete_urls_refused(self):
        """GET requests on room/user toggle and delete URLs return 405."""
        self.client.force_login(self.staff)
        post_only_urls = [
            reverse('dashboard:room_toggle', args=[self.empty_room.pk]),
            reverse('dashboard:room_delete', args=[self.empty_room.pk]),
            reverse('dashboard:user_toggle', args=[self.empty_user.pk]),
            reverse('dashboard:user_delete', args=[self.empty_user.pk]),
        ]
        for url in post_only_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 405)

    def test_inactive_user_cannot_login(self):
        """A deactivated user cannot log in and sees an inactive-account message."""
        self.client.force_login(self.staff)
        self.client.post(reverse('dashboard:user_toggle', args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

        self.client.logout()
        resp = self.client.post(reverse('accounts:login'), {
            'username': 'student.mgr',
            'password': 'Str0ngPassword!',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('inactive', resp.content.decode().lower())
        self.assertNotIn('_auth_user_id', self.client.session)


# ---------------------------------------------------------------------------
# Phase 4E: Reports (History, Print, CSV Export) Tests
# ---------------------------------------------------------------------------

class ReportsAndExportTests(TestCase):
    """Integration tests for /manage/reports/ and /manage/reports/export/."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='report_admin', password='pass', is_staff=True
        )
        self.student = User.objects.create_user(
            username='report.student',
            first_name='Maria',
            last_name='Santos',
            password='pass',
        )
        Profile.objects.create(
            user=self.student,
            user_type='student',
            college_department='College of Education',
            contact_number='09123456789',
        )
        self.other = User.objects.create_user(
            username='report.faculty',
            first_name='Pedro',
            last_name='Reyes',
            password='pass',
        )

        self.room1 = Room.objects.create(
            name='Hall A', building='Main Building', room_type='lecture', capacity=50
        )
        self.room2 = Room.objects.create(
            name='Lab B', building='IT Building', room_type='laboratory', capacity=30
        )

        self.today = timezone.localdate()
        self.tomorrow = self.today + datetime.timedelta(days=1)
        self.next_week = self.today + datetime.timedelta(days=7)

        # Approved reservation on room1 tomorrow by student
        self.res_approved = Reservation.objects.create(
            room=self.room1,
            requester=self.student,
            processed_by=self.staff,
            reservation_date=self.tomorrow,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0),
            purpose='Approved Seminar',
            num_attendees=25,
            status='approved',
        )

        # Declined reservation on room2 next_week by other (with formula-like purpose)
        self.res_declined = Reservation.objects.create(
            room=self.room2,
            requester=self.other,
            processed_by=self.staff,
            reservation_date=self.next_week,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(15, 0),
            purpose='=cmd|calc',
            num_attendees=10,
            status='declined',
            admin_remarks='Room under maintenance',
        )

        # Pending reservation on room1 tomorrow by student
        self.res_pending = Reservation.objects.create(
            room=self.room1,
            requester=self.student,
            reservation_date=self.tomorrow,
            start_time=datetime.time(14, 0),
            end_time=datetime.time(16, 0),
            purpose='Pending Study Group',
            num_attendees=15,
            status='pending',
        )

    def test_non_staff_cannot_access_reports_or_export(self):
        """Anonymous users redirect and non-staff receive 403 on reports and CSV export."""
        for url in (reverse('dashboard:reports'), reverse('dashboard:reports_export')):
            resp_anon = self.client.get(url)
            self.assertEqual(resp_anon.status_code, 302)
            self.assertIn('/accounts/login/', resp_anon['Location'])

        self.client.force_login(self.student)
        for url in (reverse('dashboard:reports'), reverse('dashboard:reports_export')):
            resp_stud = self.client.get(url)
            self.assertEqual(resp_stud.status_code, 403)

    def test_filters_work_together_and_summary_counts_are_correct(self):
        """Combining date, room, requester, and status filters narrows results and summary counts."""
        self.client.force_login(self.staff)
        url = reverse('dashboard:reports')

        # Unfiltered summary
        resp_all = self.client.get(url)
        self.assertEqual(resp_all.status_code, 200)
        self.assertEqual(resp_all.context['summary'], {
            'total': 3,
            'pending': 1,
            'approved': 1,
            'declined': 1,
            'cancelled': 0,
        })

        # Combined filter matching only res_approved
        resp_filtered = self.client.get(url, {
            'date_from': self.tomorrow.isoformat(),
            'date_to': self.tomorrow.isoformat(),
            'room': self.room1.pk,
            'requester': 'Maria',
            'status': 'approved',
        })
        self.assertEqual(resp_filtered.status_code, 200)
        self.assertEqual(resp_filtered.context['summary']['total'], 1)
        self.assertEqual(resp_filtered.context['summary']['approved'], 1)
        self.assertEqual([r.pk for r in resp_filtered.context['reservations']], [self.res_approved.pk])

    def test_invalid_date_range_shows_error(self):
        """When date_from > date_to, an error is shown and no results are returned."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('dashboard:reports'), {
            'date_from': self.next_week.isoformat(),
            'date_to': self.today.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('cannot be earlier than', resp.content.decode())
        self.assertEqual(resp.context['summary']['total'], 0)

    def test_csv_export_header_rows_and_formula_injection_neutralized(self):
        """CSV export includes expected headers/rows and prefixes =,+,-,@ cells with a quote."""
        import csv
        import io

        self.client.force_login(self.staff)
        resp = self.client.get(reverse('dashboard:reports_export'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn(f'reservations_{self.today.isoformat()}.csv', resp['Content-Disposition'])

        rows = list(csv.reader(io.StringIO(resp.content.decode('utf-8'))))
        self.assertEqual(rows[0][0], 'Date')
        self.assertEqual(rows[0][9], 'Purpose')
        self.assertEqual(len(rows), 4)  # header + 3 reservations

        purposes = [r[9] for r in rows[1:]]
        self.assertIn("'=cmd|calc", purposes)
        self.assertNotIn("=cmd|calc", purposes)

    def test_print_view_shows_university_name_and_all_rows_beyond_screen_page(self):
        """Print section includes MSU-SND header and all matching rows (even > 10) up to cap."""
        # Add 10 more reservations so total = 13 (> 10 per screen page)
        for i in range(10):
            Reservation.objects.create(
                room=self.room1,
                requester=self.student,
                reservation_date=self.tomorrow,
                start_time=datetime.time(7, 0),
                end_time=datetime.time(8, 0),
                purpose=f'Extra Print Row {i}',
                num_attendees=5,
                status='pending',
            )

        self.client.force_login(self.staff)
        resp = self.client.get(reverse('dashboard:reports'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()

        self.assertIn('Mindanao State University - Sultan Naga Dimaporo', content)
        self.assertIn('Reservation Report', content)
        # Screen page has 10, print_rows has all 13
        self.assertEqual(len(resp.context['reservations']), 10)
        self.assertEqual(len(resp.context['print_rows']), 13)
        self.assertFalse(resp.context['print_capped'])
