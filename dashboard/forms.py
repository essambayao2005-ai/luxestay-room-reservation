"""
Forms for the staff dashboard module.
Handles room creation/editing with server-side image type and size validation.
"""

import os
from django import forms
from django.core.files.uploadedfile import UploadedFile

from rooms.models import Room

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


class RoomForm(forms.ModelForm):
    """Form for adding and editing campus rooms with image upload validation."""

    class Meta:
        model = Room
        fields = ['name', 'building', 'room_type', 'capacity', 'description', 'image']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Room 201, CCS Lab 1',
            }),
            'building': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Engineering Building',
            }),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Maximum seating capacity',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional equipment notes (projector, AC, computers, etc.)',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp',
            }),
        }
        labels = {
            'name': 'Room Name',
            'building': 'Campus Building',
            'room_type': 'Room Type',
            'capacity': 'Seating Capacity',
            'description': 'Description / Equipment',
            'image': 'Room Photo (JPG, PNG, WEBP — max 2 MB)',
        }

    def clean_image(self):
        """Validate newly uploaded room images: extension, content type, and <= 2 MB."""
        image = self.cleaned_data.get('image')
        if not image or not isinstance(image, UploadedFile):
            return image

        ext = os.path.splitext(image.name or '')[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise forms.ValidationError(
                'Unsupported file extension. Please upload a JPG, JPEG, PNG, or WEBP image.'
            )

        content_type = (getattr(image, 'content_type', '') or '').lower()
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise forms.ValidationError(
                'Invalid image file type. Only JPG, PNG, and WEBP images are allowed.'
            )

        if image.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError(
                'Image file is too large. Maximum allowed size is 2 MB.'
            )

        return image
