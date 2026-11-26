"""
Views for user authentication and profile management.
Covers: register, login (with role-based redirect), logout (POST only),
and a profile page that also handles password changes.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ProfileEditForm, RegisterForm
from .models import Profile
from .permissions import get_profile

User = get_user_model()


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register(request):
    """Create a new User and a linked Profile together in one transaction.

    Using transaction.atomic() guarantees that if the Profile save fails
    (e.g. a DB error), the User is also rolled back — no orphaned accounts.
    New users are never staff; that must be set explicitly by an administrator.
    After a successful registration the user is logged in automatically.
    """
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create the User (commit=False first so we can set fields)
                    user = form.save(commit=False)
                    user.first_name = form.cleaned_data['first_name']
                    user.last_name = form.cleaned_data['last_name']
                    user.email = form.cleaned_data['email'].lower()
                    user.is_staff = False   # Registering never grants staff access
                    user.save()

                    # Create the Profile linked to this User
                    Profile.objects.create(
                        user=user,
                        user_type=form.cleaned_data['user_type'],
                        college_department=form.cleaned_data.get('college_department', ''),
                        contact_number=form.cleaned_data.get('contact_number', ''),
                    )

                # Log the new user in and send them on their way
                login(request, user)
                messages.success(
                    request,
                    f"Welcome, {user.get_full_name() or user.username}! "
                    "Your account has been created successfully."
                )

                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    url=next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect('/')

            except Exception:
                # Surface a friendly error without leaking technical details
                messages.error(
                    request,
                    "Registration failed due to a system error. Please try again."
                )
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'page_title': 'Create Account',
        'next': request.GET.get('next', ''),
    })


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class CustomLoginView(LoginView):
    """Django's built-in LoginView with two additions:
    1. redirect_authenticated_user=True — already-logged-in users skip the form.
    2. After login, staff users go to /manage/; everyone else goes to ?next or /.
       Unsafe external ?next values are ignored (url_has_allowed_host_and_scheme).
    """
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        # Staff always land on the management dashboard
        if self.request.user.is_staff:
            return '/manage/'

        # For regular users, honour a safe ?next parameter
        next_url = self.request.POST.get(
            'next',
            self.request.GET.get('next', '')
        )
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url

        return settings.LOGIN_REDIRECT_URL  # '/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Sign In'
        ctx['next'] = self.request.GET.get('next', '')
        return ctx


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def logout_view(request):
    """Log the user out via POST only.

    GET requests are silently redirected to '/' without logging out.
    This prevents CSRF-based logout via a crafted link (section 10 requirement).
    """
    if request.method == 'POST':
        logout(request)
    return redirect('/')


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@login_required
def profile(request):
    """View and edit the logged-in user's profile information.

    Uses get_or_create so users who were created outside the registration form
    (e.g. admin1 via createsuperuser) do not crash with RelatedObjectDoesNotExist.
    The profile edit form updates both the User record (name, email) and the
    Profile record (user_type, department, contact) in a single transaction.
    """
    user = request.user
    # get_or_create so admin1 / superusers without a Profile don't crash
    profile_obj, _ = Profile.objects.get_or_create(user=user)

    if request.method == 'POST':
        form = ProfileEditForm(
            request.POST,
            instance=profile_obj,
            user=user,
        )
        if form.is_valid():
            with transaction.atomic():
                # Update User fields (name, email)
                user.first_name = form.cleaned_data['first_name']
                user.last_name = form.cleaned_data['last_name']
                user.email = form.cleaned_data['email'].lower()
                user.save(update_fields=['first_name', 'last_name', 'email'])
                # Update Profile fields
                form.save()

            messages.success(request, "Your profile has been updated.")
            return redirect('accounts:profile')
    else:
        form = ProfileEditForm(instance=profile_obj, user=user)

    return render(request, 'accounts/profile.html', {
        'form': form,
        'profile': profile_obj,
        'page_title': 'My Profile',
    })


# ---------------------------------------------------------------------------
# Password Change (class-based so Django handles all edge cases)
# ---------------------------------------------------------------------------

class CustomPasswordChangeView(PasswordChangeView):
    """Password change form, reached from the profile page.

    On success, redirects back to the profile page and shows a toast message
    instead of the default /accounts/password_change/done/ page.
    Uses login_required indirectly: PasswordChangeView already requires login.
    """
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(
            self.request,
            "Your password has been changed successfully."
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Change Password'
        return ctx
