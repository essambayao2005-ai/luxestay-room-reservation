"""
Read-only database integrity verification command: `python manage.py check_data`.
Never creates, updates, or deletes any database record.
Exits with a non-zero code if any ERROR is detected.
"""

import os
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from accounts.models import Profile
from rooms.models import Reservation, Room

User = get_user_model()

VALID_STATUSES = {code for code, _ in Reservation.STATUS_CHOICES}
VALID_USER_TYPES = {code for code, _ in Profile.USER_TYPES}
LEGACY_HOTEL_NAMES = ['Luxe Ocean Suite', 'Serene Garden Villa', 'Deluxe Twin Room']


class Command(BaseCommand):
    """Read-only data integrity audit across rooms, reservations, users, and profiles."""

    help = "Read-only integrity check for rooms, reservations, users, and profiles."

    def handle(self, *args, **options):
        today = timezone.localdate()
        errors = 0
        warnings = 0

        # 1. Record counts
        total_rooms = Room.objects.count()
        active_rooms = Room.objects.filter(is_active=True).count()
        res_counts = {
            code: Reservation.objects.filter(status=code).count()
            for code, _ in Reservation.STATUS_CHOICES
        }
        total_res = Reservation.objects.count()
        total_users = User.objects.count()
        total_profiles = Profile.objects.count()

        self.stdout.write("=== Record Counts ===")
        self.stdout.write(f"Rooms: {total_rooms} total ({active_rooms} active)")
        self.stdout.write(
            f"Reservations: {total_res} total "
            f"(pending={res_counts['pending']}, approved={res_counts['approved']}, "
            f"declined={res_counts['declined']}, cancelled={res_counts['cancelled']})"
        )
        self.stdout.write(f"Users: {total_users} | Profiles: {total_profiles}")
        self.stdout.write("")
        self.stdout.write("=== Integrity Checks ===")

        def report(level, label, items):
            nonlocal errors, warnings
            if items:
                if level == 'ERROR':
                    errors += 1
                    self.stdout.write(self.style.ERROR(f"[ERROR] {label}: {items}"))
                else:
                    warnings += 1
                    self.stdout.write(self.style.WARNING(f"[WARN]  {label}: {items}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"[OK]    {label}"))

        # Check 1: end_time <= start_time (ERROR)
        bad_time_ids = list(
            Reservation.objects.filter(end_time__lte=F('start_time'))
            .values_list('id', flat=True)
        )
        report('ERROR', 'Reservations with end_time <= start_time', bad_time_ids)

        # Check 2: Overlapping APPROVED reservations for same room & date (ERROR)
        approved_list = list(
            Reservation.objects.filter(status='approved')
            .order_by('room_id', 'reservation_date', 'start_time', 'id')
            .values('id', 'room_id', 'reservation_date', 'start_time', 'end_time')
        )
        overlap_pairs = []
        for i, a in enumerate(approved_list):
            for b in approved_list[i + 1:]:
                if a['room_id'] != b['room_id'] or a['reservation_date'] != b['reservation_date']:
                    break
                if a['start_time'] < b['end_time'] and a['end_time'] > b['start_time']:
                    overlap_pairs.append(f"({a['id']}, {b['id']})")
        report('ERROR', 'Overlapping approved reservations', overlap_pairs)

        # Check 3: Unknown reservation status (ERROR)
        bad_status_ids = list(
            Reservation.objects.exclude(status__in=VALID_STATUSES)
            .values_list('id', flat=True)
        )
        report('ERROR', 'Reservations with unknown status', bad_status_ids)

        # Check 4: Approved/declined without processed_by, or declined without admin_remarks (WARN)
        no_processor_ids = list(
            Reservation.objects.filter(status__in=('approved', 'declined'), processed_by__isnull=True)
            .values_list('id', flat=True)
        )
        report('WARN', 'Approved/declined reservations without processed_by', no_processor_ids)

        no_remarks_ids = list(
            Reservation.objects.filter(status='declined', admin_remarks='')
            .values_list('id', flat=True)
        )
        report('WARN', 'Declined reservations without admin_remarks', no_remarks_ids)

        # Check 5: Pending reservations in the past (WARN)
        past_pending_ids = list(
            Reservation.objects.filter(status='pending', reservation_date__lt=today)
            .values_list('id', flat=True)
        )
        report('WARN', 'Pending reservations with date in the past', past_pending_ids)

        # Check 6: Users without Profile (WARN, usernames only) & unknown Profile user_type (ERROR)
        no_profile_usernames = list(
            User.objects.filter(profile__isnull=True).values_list('username', flat=True)
        )
        report('WARN', 'Users without a Profile (usernames)', no_profile_usernames)

        bad_user_type_ids = list(
            Profile.objects.exclude(user_type__in=VALID_USER_TYPES)
            .values_list('id', flat=True)
        )
        report('ERROR', 'Profiles with unknown user_type', bad_user_type_ids)

        # Check 7: Active rooms with capacity <= 0 or blank building (WARN)
        bad_active_room_ids = list(
            Room.objects.filter(is_active=True)
            .filter(capacity__lte=0)
            .values_list('id', flat=True)
        )
        blank_bldg_room_ids = list(
            Room.objects.filter(is_active=True, building='')
            .values_list('id', flat=True)
        )
        combined_room_warns = sorted(set(bad_active_room_ids) | set(blank_bldg_room_ids))
        report('WARN', 'Active rooms with capacity <= 0 or blank building', combined_room_warns)

        # Check 8: Rooms whose image path does not exist in MEDIA_ROOT (WARN)
        missing_img_ids = []
        media_root = str(settings.MEDIA_ROOT)
        for room in Room.objects.exclude(image='').exclude(image__isnull=True):
            full_path = os.path.join(media_root, room.image.name)
            if not os.path.exists(full_path):
                missing_img_ids.append(room.id)
        report('WARN', 'Rooms with missing image file in MEDIA_ROOT', missing_img_ids)

        # Check 9: Leftover legacy hotel rooms (WARN)
        legacy_room_ids = list(
            Room.objects.filter(name__in=LEGACY_HOTEL_NAMES)
            .values_list('id', flat=True)
        )
        report('WARN', 'Leftover legacy hotel rooms', legacy_room_ids)

        # Summary
        self.stdout.write("")
        self.stdout.write(f"Summary: {errors} ERROR(s), {warnings} WARN(s).")

        if errors > 0:
            sys.exit(1)
