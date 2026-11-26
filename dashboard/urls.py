"""
URL patterns for the dashboard app (staff/admin management module).
All views require staff privileges via @staff_required.
"""

from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('reservations/', views.reservation_list, name='reservation_list'),
    path('reservations/<int:pk>/approve/', views.reservation_approve, name='approve'),
    path('reservations/<int:pk>/decline/', views.reservation_decline, name='decline'),
]
