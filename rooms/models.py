from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Room(models.Model):
    ROOM_TYPES = [
        ('lecture', 'Lecture Room'),
        ('laboratory', 'Laboratory'),
        ('conference', 'Conference Room'),
    ]

    name = models.CharField(max_length=100)
    building = models.CharField(max_length=100, default='')
    room_type = models.CharField(max_length=50, choices=ROOM_TYPES, default='lecture')
    capacity = models.PositiveIntegerField(default=2)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='rooms/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.building})"


class Reservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
    ]

    # PROTECT: a room or user with reservations cannot be deleted (keeps history)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='reservations')
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                  related_name='reservations')
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='processed_reservations')
    reservation_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    purpose = models.CharField(max_length=255)
    num_attendees = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-reservation_date', '-start_time']

    def __str__(self):
        return (f"{self.room.name} on {self.reservation_date} "
                f"{self.start_time:%H:%M}-{self.end_time:%H:%M} ({self.status})")

    def overlapping_approved(self):
        """Approved reservations of the same room that overlap this one in time.
        Back-to-back bookings (one ends when the next starts) are allowed."""
        return Reservation.objects.filter(
            room=self.room,
            reservation_date=self.reservation_date,
            status='approved',
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
        ).exclude(pk=self.pk)

    def clean(self):
        """Validation rules (FR-04). Runs automatically in forms and in Django admin."""
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors['end_time'] = 'End time must be later than the start time.'
        if self.reservation_date and self._state.adding and self.reservation_date < timezone.localdate():
            errors['reservation_date'] = 'The date cannot be in the past.'
        if self.room_id and self.num_attendees and self.num_attendees > self.room.capacity:
            errors['num_attendees'] = f'This room only fits {self.room.capacity} people.'
        if (not errors and self.room_id and self.reservation_date and self.start_time
                and self.end_time and self.status in ('pending', 'approved')
                and self.overlapping_approved().exists()):
            raise ValidationError('This room is already reserved (approved) at that time.')
        if errors:
            raise ValidationError(errors)