"""
URL patterns for the accounts app.
Handles registration, login, logout, and user profile.
"""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('profile/password/', views.CustomPasswordChangeView.as_view(), name='password_change'),
]
