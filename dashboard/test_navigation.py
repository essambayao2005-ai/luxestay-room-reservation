"""
Phase 5A Navigation Integration Tests.
Verifies every link in the rendered sidebar and topbar for anonymous, student,
and staff users, nested active highlights, POST-only endpoints, and styled 403/404 pages.
"""

import datetime
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from rooms.models import Reservation, Room

User = get_user_model()


class _SidebarTopbarLinkParser(HTMLParser):
    """Extracts href values inside <aside class="app-sidebar"> and <header class="app-topbar">."""

    def __init__(self):
        super().__init__()
        self.in_nav_region = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        cls = attr_dict.get('class', '')
        if tag in ('aside', 'header') and ('app-sidebar' in cls or 'app-topbar' in cls):
            self.in_nav_region += 1
        elif self.in_nav_region > 0 and tag in ('aside', 'header'):
            self.in_nav_region += 1

        if self.in_nav_region > 0 and tag == 'a':
            href = attr_dict.get('href')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                self.links.append(href)

    def handle_endtag(self, tag):
        if self.in_nav_region > 0 and tag in ('aside', 'header'):
            self.in_nav_region -= 1


def _extract_nav_links(html_text):
    parser = _SidebarTopbarLinkParser()
    parser.feed(html_text)
    # Deduplicate preserving order
    return list(dict.fromkeys(parser.links))


class NavigationIntegrationTests(TestCase):
    """End-to-end navigation, role routing, POST-only, and error-page tests."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='nav_admin', password='pass', is_staff=True
        )
        self.student = User.objects.create_user(
            username='nav_student', password='pass'
        )
        Profile.objects.create(
            user=self.student,
            user_type='student',
            college_department='CCS',
            contact_number='09123456789',
        )
        self.room = Room.objects.create(
            name='Nav Room 101',
            building='Main Building',
            room_type='lecture',
            capacity=30,
            is_active=True,
        )
        self.tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.reservation = Reservation.objects.create(
            room=self.room,
            requester=self.student,
            reservation_date=self.tomorrow,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0),
            purpose='Nav Test Event',
            num_attendees=10,
            status='pending',
        )

    def _assert_all_nav_links_healthy(self, start_url):
        resp = self.client.get(start_url)
        self.assertEqual(resp.status_code, 200)
        links = _extract_nav_links(resp.content.decode())
        self.assertTrue(len(links) > 0, f"No nav links found on {start_url}")
        for href in links:
            link_resp = self.client.get(href)
            self.assertNotIn(
                link_resp.status_code,
                (404, 500),
                f"Nav link {href} returned {link_resp.status_code}",
            )

    def test_anonymous_sidebar_and_topbar_links(self):
        """Every sidebar/topbar link rendered for an anonymous visitor resolves without 404/500."""
        self._assert_all_nav_links_healthy('/')

    def test_student_sidebar_and_topbar_links(self):
        """Every sidebar/topbar link rendered for a student requester resolves without 404/500."""
        self.client.force_login(self.student)
        self._assert_all_nav_links_healthy('/')

    def test_staff_sidebar_and_topbar_links(self):
        """Every sidebar/topbar link rendered for staff resolves without 404/500."""
        self.client.force_login(self.staff)
        self._assert_all_nav_links_healthy('/manage/')

    def test_nested_pages_highlight_parent_sidebar_item_and_set_topbar_title(self):
        """Nested pages keep their parent sidebar item active and render a topbar title."""
        self.client.force_login(self.staff)
        resp_add_room = self.client.get(reverse('dashboard:room_create'))
        html = resp_add_room.content.decode()
        self.assertIn('href="/manage/rooms/" class="sidebar-link active"', html)
        self.assertIn('Add Room', html)

        self.client.force_login(self.student)
        resp_edit_res = self.client.get(
            reverse('rooms:reservation_edit', args=[self.reservation.pk])
        )
        html_edit = resp_edit_res.content.decode()
        self.assertIn('href="/my-reservations/" class="sidebar-link active"', html_edit)

    def test_post_only_urls_reject_get(self):
        """All POST-only endpoints reject GET (405, or logout redirects without logging out)."""
        self.client.force_login(self.staff)
        post_only_405 = [
            reverse('dashboard:approve', args=[self.reservation.pk]),
            reverse('dashboard:decline', args=[self.reservation.pk]),
            reverse('dashboard:room_toggle', args=[self.room.pk]),
            reverse('dashboard:room_delete', args=[self.room.pk]),
            reverse('dashboard:user_toggle', args=[self.student.pk]),
            reverse('dashboard:user_delete', args=[self.student.pk]),
        ]
        for url in post_only_405:
            self.assertEqual(self.client.get(url).status_code, 405, f"GET allowed on {url}")

        # Logout GET must not log the user out
        self.client.get(reverse('accounts:logout'))
        self.assertIn('_auth_user_id', self.client.session)

        # Requester cancel GET returns 405
        self.client.force_login(self.student)
        cancel_url = reverse('rooms:reservation_cancel', args=[self.reservation.pk])
        self.assertEqual(self.client.get(cancel_url).status_code, 405)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['*'])
    def test_unknown_url_renders_styled_404_and_non_staff_renders_403(self):
        """Unknown URLs render templates/404.html; non-staff on /manage/ render templates/403.html."""
        resp_404 = self.client.get('/this-page-does-not-exist-at-all/')
        self.assertEqual(resp_404.status_code, 404)
        self.assertIn('404 - Page Not Found', resp_404.content.decode())

        self.client.force_login(self.student)
        resp_403 = self.client.get('/manage/')
        self.assertEqual(resp_403.status_code, 403)
        self.assertIn('403 - Access Restricted', resp_403.content.decode())
