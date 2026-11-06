from django.db import models


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