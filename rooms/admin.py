from django.contrib import admin
from .models import Room, Reservation


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'building', 'room_type', 'capacity', 'is_active')
    list_filter = ('building', 'room_type', 'is_active')
    search_fields = ('name', 'building')


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('room', 'requester', 'reservation_date', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'reservation_date', 'room__building')
    search_fields = ('room__name', 'requester__username', 'purpose')