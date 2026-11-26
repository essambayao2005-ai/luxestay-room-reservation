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

    # Room management (CRUD + toggle)
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/add/', views.room_create, name='room_create'),
    path('rooms/<int:pk>/edit/', views.room_edit, name='room_edit'),
    path('rooms/<int:pk>/toggle/', views.room_toggle, name='room_toggle'),
    path('rooms/<int:pk>/delete/', views.room_delete, name='room_delete'),

    # User management (list + toggle + delete)
    path('users/', views.user_list, name='user_list'),
    path('users/<int:pk>/toggle/', views.user_toggle, name='user_toggle'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),

    # Reports (history, print, CSV export)
    path('reports/', views.reports, name='reports'),
    path('reports/export/', views.reports_export, name='reports_export'),
]
