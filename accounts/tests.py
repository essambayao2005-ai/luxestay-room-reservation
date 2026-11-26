"""
Tests for accounts Phase 4A: register, login, logout, profile.

Each test method has a one-line docstring explaining what it verifies.
Run with: python manage.py test accounts
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Profile

User = get_user_model()


class RegisterViewTests(TestCase):
    """Tests for the /accounts/register/ view."""

    def test_register_creates_user_and_profile_together(self):
        """A successful POST creates exactly one User and one linked Profile."""
        self.client.post(reverse('accounts:register'), {
            'username': 'newuser',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'new@example.com',
            'user_type': 'student',
            'college_department': 'College of Science',
            'contact_number': '09123456789',
            'password1': 'Str0ngP@ss!',
            'password2': 'Str0ngP@ss!',
        })
        user = User.objects.get(username='newuser')
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.user_type, 'student')
        self.assertEqual(user.profile.college_department, 'College of Science')

    def test_register_logs_user_in_after_success(self):
        """After a successful registration the user is immediately logged in."""
        response = self.client.post(reverse('accounts:register'), {
            'username': 'autouser',
            'first_name': 'Auto',
            'last_name': 'User',
            'email': 'auto@example.com',
            'user_type': 'faculty',
            'college_department': '',
            'contact_number': '',
            'password1': 'Str0ngP@ss!',
            'password2': 'Str0ngP@ss!',
        })
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        # Django sets _auth_user_id in the session when a user is logged in
        self.assertIn('_auth_user_id', self.client.session)

    def test_register_new_user_is_not_staff(self):
        """Users registered through the register form are never marked as staff."""
        self.client.post(reverse('accounts:register'), {
            'username': 'stafftest',
            'first_name': 'S',
            'last_name': 'T',
            'email': 'st@example.com',
            'user_type': 'student',
            'college_department': '',
            'contact_number': '',
            'password1': 'Str0ngP@ss!',
            'password2': 'Str0ngP@ss!',
        })
        user = User.objects.get(username='stafftest')
        self.assertFalse(user.is_staff)

    def test_duplicate_username_is_refused(self):
        """Submitting a username that already exists is rejected with an error."""
        User.objects.create_user(username='taken', password='pass12345')
        response = self.client.post(reverse('accounts:register'), {
            'username': 'taken',
            'first_name': 'A',
            'last_name': 'B',
            'email': 'unique@example.com',
            'user_type': 'student',
            'college_department': '',
            'contact_number': '',
            'password1': 'Str0ngP@ss!',
            'password2': 'Str0ngP@ss!',
        })
        self.assertEqual(response.status_code, 200)   # re-renders the form
        self.assertFalse(User.objects.filter(email='unique@example.com').exists())

    def test_duplicate_email_is_refused(self):
        """Submitting an email already in use is rejected with an error."""
        User.objects.create_user(username='first', email='same@example.com', password='pass12345')
        response = self.client.post(reverse('accounts:register'), {
            'username': 'second',
            'first_name': 'B',
            'last_name': 'C',
            'email': 'same@example.com',
            'user_type': 'student',
            'college_department': '',
            'contact_number': '',
            'password1': 'Str0ngP@ss!',
            'password2': 'Str0ngP@ss!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='second').exists())

    def test_rollback_if_profile_save_fails(self):
        """If the Profile.objects.create() raises, the User is also rolled back.

        We simulate a DB error by patching Profile.objects.create to raise.
        """
        from unittest.mock import patch
        with patch('accounts.models.Profile.objects.create', side_effect=Exception("DB error")):
            self.client.post(reverse('accounts:register'), {
                'username': 'rollbackuser',
                'first_name': 'R',
                'last_name': 'U',
                'email': 'rollback@example.com',
                'user_type': 'student',
                'college_department': '',
                'contact_number': '',
                'password1': 'Str0ngP@ss!',
                'password2': 'Str0ngP@ss!',
            })
        # The User must NOT exist because the transaction was rolled back
        self.assertFalse(User.objects.filter(username='rollbackuser').exists())


class LoginViewTests(TestCase):
    """Tests for the /accounts/login/ view."""

    def setUp(self):
        """Create a normal user and a staff user for login tests."""
        self.user = User.objects.create_user(
            username='normaluser', password='Str0ngP@ss!'
        )
        self.staff = User.objects.create_user(
            username='adminuser', password='Str0ngP@ss!', is_staff=True
        )

    def test_normal_user_redirects_to_root(self):
        """After login, a normal (non-staff) user is sent to '/'."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'normaluser',
            'password': 'Str0ngP@ss!',
        })
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_staff_user_redirects_to_manage(self):
        """After login, a staff user is sent to /manage/ regardless of ?next."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'adminuser',
            'password': 'Str0ngP@ss!',
        })
        self.assertRedirects(response, '/manage/', fetch_redirect_response=False)

    def test_safe_next_is_honoured_for_normal_user(self):
        """A safe ?next URL on this site is followed after a normal-user login."""
        login_url = reverse('accounts:login') + '?next=/accounts/profile/'
        response = self.client.post(login_url, {
            'username': 'normaluser',
            'password': 'Str0ngP@ss!',
            'next': '/accounts/profile/',
        })
        self.assertRedirects(
            response, '/accounts/profile/', fetch_redirect_response=False
        )

    def test_unsafe_next_is_ignored(self):
        """An external ?next= URL (https://evil.com) is ignored; user goes to '/'."""
        login_url = reverse('accounts:login') + '?next=https://evil.com'
        response = self.client.post(login_url, {
            'username': 'normaluser',
            'password': 'Str0ngP@ss!',
            'next': 'https://evil.com',
        })
        # Should NOT redirect to the external URL
        self.assertNotEqual(response['Location'], 'https://evil.com')
        # Should end up at '/' (LOGIN_REDIRECT_URL)
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_staff_next_is_always_manage(self):
        """Staff always go to /manage/ even if a safe ?next= is supplied."""
        login_url = reverse('accounts:login') + '?next=/accounts/profile/'
        response = self.client.post(login_url, {
            'username': 'adminuser',
            'password': 'Str0ngP@ss!',
            'next': '/accounts/profile/',
        })
        self.assertRedirects(response, '/manage/', fetch_redirect_response=False)


class LogoutViewTests(TestCase):
    """Tests for the /accounts/logout/ view."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutuser', password='Str0ngP@ss!'
        )
        self.client.login(username='logoutuser', password='Str0ngP@ss!')

    def test_logout_requires_post(self):
        """A GET request to the logout URL does NOT log the user out."""
        response = self.client.get(reverse('accounts:logout'))
        # Redirected to '/' but still logged in
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        # Session should still contain the auth user (not logged out)
        self.assertIn('_auth_user_id', self.client.session)

    def test_post_logout_logs_user_out(self):
        """A POST request to the logout URL logs the user out and redirects to '/'."""
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)


class ProfileViewTests(TestCase):
    """Tests for the /accounts/profile/ view."""

    def setUp(self):
        """Create a normal user (with Profile) and a user without a Profile."""
        self.user = User.objects.create_user(
            username='profileuser', password='Str0ngP@ss!',
            first_name='Profile', last_name='User', email='pu@example.com'
        )
        Profile.objects.create(
            user=self.user, user_type='student',
            college_department='CS Dept', contact_number='09111111111'
        )

        # Simulates admin1: a user created via createsuperuser with no Profile
        self.no_profile_user = User.objects.create_user(
            username='noprofile', password='Str0ngP@ss!'
        )

    def test_anonymous_user_is_redirected_from_profile(self):
        """An unauthenticated request to /accounts/profile/ redirects to login."""
        response = self.client.get(reverse('accounts:profile'))
        self.assertRedirects(
            response,
            '/accounts/login/?next=/accounts/profile/',
            fetch_redirect_response=False,
        )

    def test_profile_page_loads_for_authenticated_user(self):
        """An authenticated user can access their profile page (HTTP 200)."""
        self.client.login(username='profileuser', password='Str0ngP@ss!')
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)

    def test_profile_page_works_for_user_without_a_profile(self):
        """A user with no Profile record (e.g. admin1) does not crash the page."""
        self.client.login(username='noprofile', password='Str0ngP@ss!')
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        # A Profile must have been created by get_or_create
        self.assertTrue(Profile.objects.filter(user=self.no_profile_user).exists())

    def test_profile_edit_saves_user_and_profile(self):
        """Posting to /accounts/profile/ updates both User and Profile fields."""
        self.client.login(username='profileuser', password='Str0ngP@ss!')
        self.client.post(reverse('accounts:profile'), {
            'first_name': 'Updated',
            'last_name': 'Name',
            'email': 'updated@example.com',
            'user_type': 'faculty',
            'college_department': 'Education Dept',
            'contact_number': '09999999999',
        })
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.profile.user_type, 'faculty')
