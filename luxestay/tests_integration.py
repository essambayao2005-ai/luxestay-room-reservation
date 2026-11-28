"""
Phase 5B: End-to-End Integration Tests, Permissions Matrix, and Query-Count Bounds.
Creates isolated test data; never relies on seeded or production rows.
Run with: python manage.py test luxestay.tests_integration
"""

import csv
import datetime
import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Profile
from rooms.availability import rooms_with_status
from rooms.models import Reservation, Room

User = get_user_model()


class EndToEndFlowsTests(TestCase):
    """End-to-end user journeys across accounts, rooms, and dashboard."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='e2e_admin', email='admin@msu.edu.ph', password='Password123!', is_staff=True
        )
        self.other_student = User.objects.create_user(
            username='e2e_other', email='other@msu.edu.ph', password='Password123!'
        )
        Profile.objects.create(
            user=self.other_student, user_type='student', college_department='CCS'
        )
        self.room = Room.objects.create(
            name='E2E Lecture 101',
            building='Main Building',
            room_type='lecture',
            capacity=40,
            is_active=True,
        )
        self.tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.yesterday = timezone.localdate() - datetime.timedelta(days=1)

    def test_a_happy_path_register_to_approve_to_occupied_and_privacy(self):
        """Register -> search -> reserve -> staff approve -> Occupied & board privacy -> overlap refused."""
        # 1. Register a new student
        reg_resp = self.client.post(reverse('accounts:register'), {
            'username': 'e2e_student',
            'first_name': 'Ana',
            'last_name': 'Reyes',
            'email': 'ana@msu.edu.ph',
            'user_type': 'student',
            'college_department': 'COE',
            'contact_number': '09171234567',
            'password1': 'Str0ngPass!99',
            'password2': 'Str0ngPass!99',
        })
        self.assertRedirects(reg_resp, '/', fetch_redirect_response=False)
        student = User.objects.get(username='e2e_student')
        self.assertTrue(Profile.objects.filter(user=student).exists())

        # 2. Search availability -> room is Available
        tom_str = self.tomorrow.isoformat()
        search_resp = self.client.get(f'/?date={tom_str}&start_time=09:00&end_time=11:00')
        self.assertEqual(search_resp.status_code, 200)
        self.assertFalse(search_resp.context['rooms'][0].is_occupied)

        # 3. Reserve -> Pending -> appears in My Reservations
        create_url = reverse('rooms:reservation_create', args=[self.room.pk])
        res_resp = self.client.post(create_url, {
            'reservation_date': tom_str,
            'start_time': '09:00',
            'end_time': '11:00',
            'purpose': 'Secret Thesis Defense',
            'num_attendees': 20,
        })
        self.assertRedirects(res_resp, reverse('rooms:my_reservations'))
        my_resp = self.client.get(reverse('rooms:my_reservations'))
        self.assertIn('Pending', my_resp.content.decode())
        reservation = Reservation.objects.get(purpose='Secret Thesis Defense')

        # 4. Staff logs in, sees pending count, and approves
        self.client.force_login(self.staff)
        dash_resp = self.client.get(reverse('dashboard:home'))
        self.assertEqual(dash_resp.context['pending_count'], 1)
        self.client.post(reverse('dashboard:approve', args=[reservation.pk]))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, 'approved')

        # 5. Requester sees Approved in My Reservations
        self.client.force_login(student)
        my_resp2 = self.client.get(reverse('rooms:my_reservations'))
        self.assertIn('Approved', my_resp2.content.decode())

        # 6. rooms_with_status marks room Occupied for that slot
        qs = list(rooms_with_status(
            date=self.tomorrow,
            start_time=datetime.time(9, 30),
            end_time=datetime.time(10, 30),
        ))
        self.assertTrue(qs[0].is_occupied)

        # 7. Visitor on Availability Board sees 'Reserved' + time, NEVER purpose or name
        self.client.logout()
        board_resp = self.client.get(reverse('rooms:availability_board') + f'?date={tom_str}')
        board_html = board_resp.content.decode()
        self.assertIn('Reserved', board_html)
        self.assertNotIn('Secret Thesis Defense', board_html)
        self.assertNotIn('Ana Reyes', board_html)

        # 8. Another user's overlapping request is refused with a clear message
        self.client.force_login(self.other_student)
        overlap_resp = self.client.post(create_url, {
            'reservation_date': tom_str,
            'start_time': '10:00',
            'end_time': '12:00',
            'purpose': 'Conflicting Event',
            'num_attendees': 10,
        })
        self.assertEqual(overlap_resp.status_code, 200)
        self.assertIn('already reserved (approved)', overlap_resp.content.decode())

    def test_b_decline_requires_remarks_and_keeps_slot_available(self):
        """Declining requires remarks; requester sees Declined + remarks; slot stays free."""
        res = Reservation.objects.create(
            room=self.room,
            requester=self.other_student,
            reservation_date=self.tomorrow,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(15, 0),
            purpose='Decline Flow',
            num_attendees=10,
            status='pending',
        )
        self.client.force_login(self.staff)
        decline_url = reverse('dashboard:decline', args=[res.pk])

        # Blank remarks refused
        resp_blank = self.client.post(decline_url, {'admin_remarks': ''}, follow=True)
        res.refresh_from_db()
        self.assertEqual(res.status, 'pending')
        self.assertIn('remarks are required', resp_blank.content.decode())

        # Valid remarks succeeds
        self.client.post(decline_url, {'admin_remarks': 'Facility maintenance'})
        res.refresh_from_db()
        self.assertEqual(res.status, 'declined')

        # Requester sees Declined and remarks
        self.client.force_login(self.other_student)
        my_html = self.client.get(reverse('rooms:my_reservations')).content.decode()
        self.assertIn('Declined', my_html)
        self.assertIn('Facility maintenance', my_html)

        # Slot remains available
        qs = list(rooms_with_status(self.tomorrow, datetime.time(13, 0), datetime.time(15, 0)))
        self.assertFalse(qs[0].is_occupied)

    def test_c_cancel_rules_owner_approved_and_other_user_404(self):
        """Owner can cancel pending; approved cannot be cancelled; other user gets 404."""
        pending = Reservation.objects.create(
            room=self.room, requester=self.other_student,
            reservation_date=self.tomorrow, start_time=datetime.time(8, 0),
            end_time=datetime.time(9, 0), purpose='Cancelable', num_attendees=5, status='pending',
        )
        approved = Reservation.objects.create(
            room=self.room, requester=self.other_student, processed_by=self.staff,
            reservation_date=self.tomorrow, start_time=datetime.time(15, 0),
            end_time=datetime.time(16, 0), purpose='Locked', num_attendees=5, status='approved',
        )

        # Another user gets 404
        intruder = User.objects.create_user(username='intruder', password='pass')
        self.client.force_login(intruder)
        self.assertEqual(
            self.client.post(reverse('rooms:reservation_cancel', args=[pending.pk])).status_code, 404
        )

        # Owner cancels pending
        self.client.force_login(self.other_student)
        self.client.post(reverse('rooms:reservation_cancel', args=[pending.pk]))
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'cancelled')

        # Owner cannot cancel approved
        self.client.post(reverse('rooms:reservation_cancel', args=[approved.pk]))
        approved.refresh_from_db()
        self.assertEqual(approved.status, 'approved')

    def test_d_edit_pending_revalidates_and_approved_cannot_be_edited(self):
        """Editing pending re-checks past/capacity/overlap; approved cannot be edited."""
        approved = Reservation.objects.create(
            room=self.room, requester=self.other_student, processed_by=self.staff,
            reservation_date=self.tomorrow, start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0), purpose='Approved Slot', num_attendees=5, status='approved',
        )
        pending = Reservation.objects.create(
            room=self.room, requester=self.other_student,
            reservation_date=self.tomorrow, start_time=datetime.time(13, 0),
            end_time=datetime.time(14, 0), purpose='Editable', num_attendees=5, status='pending',
        )
        self.client.force_login(self.other_student)

        # Approved cannot be edited
        resp_app = self.client.get(reverse('rooms:reservation_edit', args=[approved.pk]), follow=True)
        self.assertRedirects(resp_app, reverse('rooms:my_reservations'))

        edit_url = reverse('rooms:reservation_edit', args=[pending.pk])
        # Past date refused
        resp_past = self.client.post(edit_url, {
            'reservation_date': self.yesterday.isoformat(), 'start_time': '13:00',
            'end_time': '14:00', 'purpose': 'Editable', 'num_attendees': 5,
        })
        self.assertIn('cannot be in the past', resp_past.content.decode())

        # Over capacity refused
        resp_cap = self.client.post(edit_url, {
            'reservation_date': self.tomorrow.isoformat(), 'start_time': '13:00',
            'end_time': '14:00', 'purpose': 'Editable', 'num_attendees': 99,
        })
        self.assertIn('only fits 40 people', resp_cap.content.decode())

        # Overlap refused
        resp_ov = self.client.post(edit_url, {
            'reservation_date': self.tomorrow.isoformat(), 'start_time': '10:30',
            'end_time': '11:30', 'purpose': 'Editable', 'num_attendees': 5,
        })
        self.assertIn('already reserved (approved)', resp_ov.content.decode())

    def test_e_two_overlapping_pending_conflict_workflow(self):
        """Approving first pending flags second as CONFLICT, blocks approval, allows decline."""
        r1 = Reservation.objects.create(
            room=self.room, requester=self.other_student,
            reservation_date=self.tomorrow, start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0), purpose='First Req', num_attendees=10, status='pending',
        )
        r2 = Reservation.objects.create(
            room=self.room, requester=self.other_student,
            reservation_date=self.tomorrow, start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0), purpose='Second Req', num_attendees=10, status='pending',
        )
        self.client.force_login(self.staff)
        self.client.post(reverse('dashboard:approve', args=[r1.pk]))

        # Second shows conflict flag
        list_resp = self.client.get(reverse('dashboard:reservation_list') + '?tab=pending')
        self.assertTrue(list_resp.context['reservations'][0].has_conflict)

        # Cannot approve second
        self.client.post(reverse('dashboard:approve', args=[r2.pk]))
        r2.refresh_from_db()
        self.assertEqual(r2.status, 'pending')

        # Can decline second
        self.client.post(reverse('dashboard:decline', args=[r2.pk]), {'admin_remarks': 'Slot taken'})
        r2.refresh_from_db()
        self.assertEqual(r2.status, 'declined')

    def test_f_staff_rooms_image_toggle_and_delete_protection(self):
        """Staff adds room with image, deactivates (hides + 404 reserve), delete protected vs empty."""
        tmp_media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=tmp_media):
                self.client.force_login(self.staff)
                buf = io.BytesIO()
                Image.new('RGB', (10, 10)).save(buf, format='PNG')
                img = SimpleUploadedFile('new_room.png', buf.getvalue(), content_type='image/png')

                self.client.post(reverse('dashboard:room_create'), {
                    'name': 'New Photo Lab', 'building': 'IT', 'room_type': 'laboratory',
                    'capacity': 25, 'image': img,
                })
                new_room = Room.objects.get(name='New Photo Lab')
                self.assertIn('New Photo Lab', self.client.get('/').content.decode())

                # Deactivate -> hidden from '/' and /reserve/<id>/ returns 404
                self.client.post(reverse('dashboard:room_toggle', args=[new_room.pk]), follow=True)
                self.assertNotIn(new_room, self.client.get('/').context['rooms'])
                self.assertEqual(
                    self.client.get(reverse('rooms:reservation_create', args=[new_room.pk])).status_code,
                    404,
                )

                # Delete empty room works
                self.client.post(reverse('dashboard:room_delete', args=[new_room.pk]))
                self.assertFalse(Room.objects.filter(pk=new_room.pk).exists())

                # Delete room with reservation refused
                Reservation.objects.create(
                    room=self.room, requester=self.other_student,
                    reservation_date=self.tomorrow, start_time=datetime.time(8, 0),
                    end_time=datetime.time(9, 0), purpose='Keep Room', num_attendees=5,
                )
                resp_prot = self.client.post(
                    reverse('dashboard:room_delete', args=[self.room.pk]), follow=True
                )
                self.assertTrue(Room.objects.filter(pk=self.room.pk).exists())
                self.assertIn('existing reservations', resp_prot.content.decode())
        finally:
            shutil.rmtree(tmp_media, ignore_errors=True)

    def test_g_staff_users_deactivate_self_protection_and_delete_protection(self):
        """Deactivating user blocks login; admin cannot deactivate/delete self; protected user kept."""
        self.client.force_login(self.staff)
        # Self-protection
        self.client.post(reverse('dashboard:user_toggle', args=[self.staff.pk]))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)
        self.client.post(reverse('dashboard:user_delete', args=[self.staff.pk]))
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

        # User with reservation cannot be deleted
        Reservation.objects.create(
            room=self.room, requester=self.other_student,
            reservation_date=self.tomorrow, start_time=datetime.time(8, 0),
            end_time=datetime.time(9, 0), purpose='Keep User', num_attendees=5,
        )
        self.client.post(reverse('dashboard:user_delete', args=[self.other_student.pk]))
        self.assertTrue(User.objects.filter(pk=self.other_student.pk).exists())

        # Deactivate other_student -> login fails with inactive message
        self.client.post(reverse('dashboard:user_toggle', args=[self.other_student.pk]))
        self.client.logout()
        login_resp = self.client.post(reverse('accounts:login'), {
            'username': 'e2e_other', 'password': 'Password123!',
        })
        self.assertIn('inactive', login_resp.content.decode().lower())

    def test_h_reports_filters_summary_and_csv_match_database(self):
        """Reports filters, summary counts, and CSV export rows match the database."""
        Reservation.objects.create(
            room=self.room, requester=self.other_student, processed_by=self.staff,
            reservation_date=self.tomorrow, start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0), purpose='Report Approved', num_attendees=10, status='approved',
        )
        Reservation.objects.create(
            room=self.room, requester=self.other_student,
            reservation_date=self.tomorrow, start_time=datetime.time(13, 0),
            end_time=datetime.time(14, 0), purpose='Report Pending', num_attendees=10, status='pending',
        )
        self.client.force_login(self.staff)
        rep_resp = self.client.get(reverse('dashboard:reports') + '?status=approved')
        self.assertEqual(rep_resp.context['summary']['total'], 1)
        self.assertEqual(rep_resp.context['summary']['approved'], 1)

        csv_resp = self.client.get(reverse('dashboard:reports_export') + '?status=approved')
        rows = list(csv.reader(io.StringIO(csv_resp.content.decode('utf-8'))))
        self.assertEqual(len(rows), 2)  # header + 1 approved row
        self.assertEqual(rows[1][9], 'Report Approved')

    def test_i_permissions_matrix_across_all_urls(self):
        """Table-driven permissions matrix for anonymous, student, and staff across all URLs."""
        matrix = [
            (reverse('rooms:room_list'), 200, 200, 200),
            (reverse('rooms:availability_board'), 200, 200, 200),
            (reverse('accounts:login'), 200, 302, 302),
            (reverse('accounts:register'), 200, 302, 302),
            (reverse('accounts:profile'), 302, 200, 200),
            (reverse('rooms:reservation_create', args=[self.room.pk]), 302, 200, 200),
            (reverse('rooms:my_reservations'), 302, 200, 200),
            (reverse('dashboard:home'), 302, 403, 200),
            (reverse('dashboard:reservation_list'), 302, 403, 200),
            (reverse('dashboard:room_list'), 302, 403, 200),
            (reverse('dashboard:room_create'), 302, 403, 200),
            (reverse('dashboard:user_list'), 302, 403, 200),
            (reverse('dashboard:reports'), 302, 403, 200),
            (reverse('dashboard:reports_export'), 302, 403, 200),
        ]

        # 1. Anonymous
        self.client.logout()
        for url, expected_anon, _, _ in matrix:
            self.assertEqual(self.client.get(url).status_code, expected_anon, f"Anon {url}")

        # 2. Student
        self.client.force_login(self.other_student)
        for url, _, expected_stud, _ in matrix:
            self.assertEqual(self.client.get(url).status_code, expected_stud, f"Student {url}")

        # 3. Staff
        self.client.force_login(self.staff)
        for url, _, _, expected_staff in matrix:
            self.assertEqual(self.client.get(url).status_code, expected_staff, f"Staff {url}")


class QueryCountBoundsTests(TestCase):
    """Verify key pages execute a small, bounded number of SQL queries (no N+1)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='q_admin', password='pass', is_staff=True
        )
        self.student = User.objects.create_user(
            username='q_student', password='pass'
        )
        Profile.objects.create(
            user=self.student, user_type='student', college_department='CCS'
        )
        self.rooms = [
            Room.objects.create(name=f'Q Room {i}', building='Bldg A', capacity=30)
            for i in range(5)
        ]
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        for i in range(15):
            Reservation.objects.create(
                room=self.rooms[i % 5],
                requester=self.student,
                reservation_date=tomorrow,
                start_time=datetime.time(8, 0),
                end_time=datetime.time(9, 0),
                purpose=f'Query Test {i}',
                num_attendees=10,
                status='pending' if i % 2 == 0 else 'approved',
            )

    def _assert_max_queries(self, url, max_queries):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(
            len(ctx),
            max_queries,
            f"{url} executed {len(ctx)} queries (limit {max_queries})",
        )

    def test_public_and_requester_query_bounds(self):
        """Rooms list, Availability Board, and My Reservations (15 rows) stay within query bounds."""
        self._assert_max_queries('/', 10)
        self._assert_max_queries('/board/', 10)

        self.client.force_login(self.student)
        self._assert_max_queries(reverse('rooms:my_reservations'), 10)

    def test_staff_dashboard_query_bounds(self):
        """Dashboard home, staff reservations (15 rows), and reports stay within query bounds."""
        self.client.force_login(self.staff)
        self._assert_max_queries(reverse('dashboard:home'), 15)
        self._assert_max_queries(reverse('dashboard:reservation_list') + '?tab=history', 12)
        self._assert_max_queries(reverse('dashboard:reports'), 12)
