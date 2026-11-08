"""
Forms for the rooms app.
Handles room search and availability queries.
"""

from django import forms
from django.utils import timezone
from .availability import get_buildings


class RoomSearchForm(forms.Form):
    """GET search form for filtering campus rooms and checking time-slot availability."""

    date = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
                'aria-label': 'Reservation Date',
            }
        ),
    )
    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            attrs={
                'type': 'time',
                'class': 'form-control',
                'aria-label': 'Start Time',
            }
        ),
    )
    end_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            attrs={
                'type': 'time',
                'class': 'form-control',
                'aria-label': 'End Time',
            }
        ),
    )
    building = forms.ChoiceField(
        required=False,
        widget=forms.Select(
            attrs={
                'class': 'form-select',
                'aria-label': 'Campus Building',
            }
        ),
    )
    min_capacity = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Min capacity',
                'min': '1',
                'aria-label': 'Minimum Capacity',
            }
        ),
    )
    available_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                'class': 'form-check-input',
                'id': 'availableOnlyCheck',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate dynamic building choices from active campus rooms
        buildings = get_buildings()
        self.fields['building'].choices = [('', 'All Buildings')] + [
            (b, b) for b in buildings
        ]

        # When the form is unbound, prefill the date field with today
        if not self.is_bound and not self.initial.get('date'):
            self.initial['date'] = timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        # Validate date is not in the past
        if date and date < timezone.localdate():
            self.add_error(
                'date',
                'Please select today or a future date. Past dates cannot be searched.',
            )

        # If time slot fields are used, validate start and end relationships
        if start_time and end_time:
            if end_time <= start_time:
                self.add_error(
                    'end_time',
                    'End time must be later than start time.',
                )
            if not date:
                self.add_error(
                    'date',
                    'Please select a date for the requested time slot.',
                )
        elif start_time and not end_time:
            self.add_error(
                'end_time',
                'Please specify an end time for the requested time slot.',
            )
        elif end_time and not start_time:
            self.add_error(
                'start_time',
                'Please specify a start time for the requested time slot.',
            )

        return cleaned_data
