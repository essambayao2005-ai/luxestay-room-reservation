from django.contrib import admin
from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'capacity', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)