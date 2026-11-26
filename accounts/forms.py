"""
Forms for user registration and profile editing.
RegisterForm extends UserCreationForm so Django's built-in password
validators and double-entry check are inherited for free.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Profile

User = get_user_model()


class RegisterForm(UserCreationForm):
    """Registration form that creates a User and a Profile together.

    Fields beyond the standard UserCreationForm:
    - first_name, last_name: stored on the User model.
    - email: required and must be unique across all users.
    - user_type, college_department, contact_number: stored on Profile.
    """

    first_name = forms.CharField(
        max_length=150,
        required=True,
        label='First Name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name',
            'autocomplete': 'given-name',
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label='Last Name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name',
            'autocomplete': 'family-name',
        }),
    )
    email = forms.EmailField(
        required=True,
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
        }),
    )
    user_type = forms.ChoiceField(
        choices=Profile.USER_TYPES,
        required=True,
        label='User Type',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    college_department = forms.CharField(
        max_length=100,
        required=False,
        label='College / Department',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. College of Engineering',
            'autocomplete': 'organization',
        }),
    )
    contact_number = forms.CharField(
        max_length=20,
        required=False,
        label='Contact Number',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '09xxxxxxxxx',
            'autocomplete': 'tel',
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'user_type', 'college_department', 'contact_number',
            'password1', 'password2',
        ]
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username',
                'autocomplete': 'username',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply Bootstrap class to the inherited password fields
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Create a password',
            'autocomplete': 'new-password',
            'id': 'id_password1',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
            'id': 'id_password2',
        })

    def clean_email(self):
        """Reject duplicate email addresses across all User records."""
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email address already exists.'
            )
        return email


class ProfileEditForm(forms.ModelForm):
    """Form for editing the user's basic info (name, email) and Profile fields.

    The form is backed by Profile but we also update User fields (name, email)
    in the view using save(commit=False) so the two records stay in sync.
    """

    first_name = forms.CharField(
        max_length=150,
        required=True,
        label='First Name',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        label='Last Name',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    email = forms.EmailField(
        required=True,
        label='Email Address',
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = Profile
        fields = ['user_type', 'college_department', 'contact_number']
        widgets = {
            'user_type': forms.Select(attrs={'class': 'form-select'}),
            'college_department': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate User fields from the User instance passed in
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
        self._user = user

    def clean_email(self):
        """Reject duplicate emails, excluding the current user's own record."""
        email = self.cleaned_data.get('email', '').strip().lower()
        User = get_user_model()
        qs = User.objects.filter(email__iexact=email)
        if self._user:
            qs = qs.exclude(pk=self._user.pk)
        if qs.exists():
            raise forms.ValidationError(
                'An account with this email address already exists.'
            )
        return email
