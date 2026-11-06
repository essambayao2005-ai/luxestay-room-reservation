from django.conf import settings
from django.db import models


class Profile(models.Model):
    USER_TYPES = [
        ('student', 'Student / Organization Officer'),
        ('faculty', 'Faculty / Instructor'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='student')
    college_department = models.CharField(max_length=100, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_user_type_display()})"