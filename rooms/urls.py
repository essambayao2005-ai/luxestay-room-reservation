"""
URL patterns for the rooms app.
Maps the room list and availability search view.
"""

from django.urls import path
from . import views

app_name = 'rooms'

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('board/', views.availability_board, name='availability_board'),
]

