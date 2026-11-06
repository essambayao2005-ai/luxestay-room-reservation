from django.contrib import admin
from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'building', 'room_type', 'capacity', 'is_active')
    list_filter = ('building', 'room_type', 'is_active')
    search_fields = ('name', 'building')