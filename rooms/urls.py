"""
URL patterns for the rooms app.
Maps room directory, availability board, and requester reservation flows.
"""

from django.urls import path
from . import views

app_name = 'rooms'

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('board/', views.availability_board, name='availability_board'),
    path('reserve/<int:room_id>/', views.reservation_create, name='reservation_create'),
    path('my-reservations/', views.my_reservations, name='my_reservations'),
    path('my-reservations/<int:pk>/edit/', views.reservation_edit, name='reservation_edit'),
    path('my-reservations/<int:pk>/cancel/', views.reservation_cancel, name='reservation_cancel'),
]
