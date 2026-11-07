import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from rooms.models import Room, Reservation


class Command(BaseCommand):
    """Management command to seed school rooms, create demo users and reservations,
    or clean up legacy hotel test data."""

    help = "Seeds campus rooms, demo accounts, and sample reservations for development."

    def add_arguments(self, parser):
        parser.add_argument(
            '--demo',
            action='store_true',
            help='Create demo faculty and student accounts with sample reservations relative to today.',
        )
        parser.add_argument(
            '--clear-test-data',
            action='store_true',
            help='Find and remove legacy hotel test rooms (with blank building) and their reservations.',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Explicit confirmation flag required to execute data deletion for --clear-test-data.',
        )

    def handle(self, *args, **options):
        # 1. Handle clearing legacy hotel test data if requested
        if options['clear_test_data']:
            self.handle_clear_test_data(options['yes'])
            if not options['demo']:
                return

        # 2. Always ensure the 8 standard school rooms exist (idempotent)
        rooms_dict = self.seed_school_rooms()

        # 3. Handle demo users and reservations if requested
        if options['demo']:
            self.seed_demo_data(rooms_dict)

    def seed_school_rooms(self):
        """Creates the 8 campus rooms specified in the project roadmap if they do not exist.
        Matches by name and building to prevent duplicate entries."""
        school_rooms_data = [
            {
                'name': 'CCS Lab 1',
                'building': 'IT Building',
                'room_type': 'laboratory',
                'capacity': 40,
                'description': 'Computer laboratory equipped with 40 workstations for programming and networking classes.',
            },
            {
                'name': 'CCS Lab 2',
                'building': 'IT Building',
                'room_type': 'laboratory',
                'capacity': 40,
                'description': 'Advanced computer laboratory with 40 multimedia and software engineering workstations.',
            },
            {
                'name': 'Room 201',
                'building': 'CS Building',
                'room_type': 'lecture',
                'capacity': 50,
                'description': 'Standard lecture hall with digital projector, audio system, and whiteboard.',
            },
            {
                'name': 'Room 202',
                'building': 'CS Building',
                'room_type': 'lecture',
                'capacity': 45,
                'description': 'Air-conditioned multimedia classroom suitable for departmental lectures.',
            },
            {
                'name': 'Conference Room',
                'building': 'CCS Office',
                'room_type': 'conference',
                'capacity': 20,
                'description': 'Executive conference room with central conference table and video conferencing setup.',
            },
            {
                'name': 'Seminar Room',
                'building': 'Library',
                'room_type': 'conference',
                'capacity': 30,
                'description': 'Acoustically treated seminar room designed for thesis defenses and faculty presentations.',
            },
            {
                'name': 'Engineering Lab',
                'building': 'Engineering Building',
                'room_type': 'laboratory',
                'capacity': 35,
                'description': 'Specialized engineering laboratory with hardware test benches and electrical workstations.',
            },
            {
                'name': 'Lecture Hall 1',
                'building': 'Engineering Building',
                'room_type': 'lecture',
                'capacity': 80,
                'description': 'Tiered auditorium lecture hall suited for large collegiate classes and assemblies.',
            },
        ]

        created_count = 0
        existing_count = 0
        rooms_by_name = {}

        for rdata in school_rooms_data:
            room, created = Room.objects.get_or_create(
                name=rdata['name'],
                building=rdata['building'],
                defaults={
                    'room_type': rdata['room_type'],
                    'capacity': rdata['capacity'],
                    'description': rdata['description'],
                    'is_active': True,
                },
            )
            rooms_by_name[room.name] = room
            if created:
                created_count += 1
            else:
                existing_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[Rooms] Processed 8 school rooms ({created_count} created, {existing_count} already existed)."
            )
        )
        return rooms_by_name

    def handle_clear_test_data(self, confirmed):
        """Finds legacy hotel rooms and their linked reservations.
        Requires --yes to perform actual deletion; otherwise performs a dry run."""
        hotel_names = ['Luxe Ocean Suite', 'Serene Garden Villa', 'Deluxe Twin Room']
        hotel_rooms = Room.objects.filter(name__in=hotel_names, building='')
        hotel_reservations = Reservation.objects.filter(room__in=hotel_rooms)

        res_count = hotel_reservations.count()
        room_count = hotel_rooms.count()

        if room_count == 0 and res_count == 0:
            self.stdout.write(
                self.style.NOTICE("[Clear Test Data] No legacy hotel test data found in database.")
            )
            return

        if not confirmed:
            self.stdout.write(
                self.style.WARNING(
                    f"[Dry Run] Found {room_count} legacy room(s) and {res_count} linked reservation(s) to delete:"
                )
            )
            for res in hotel_reservations:
                self.stdout.write(
                    f"  - Reservation #{res.id}: Room '{res.room.name}', Date {res.reservation_date}, Purpose '{res.purpose}'"
                )
            for room in hotel_rooms:
                self.stdout.write(
                    f"  - Room #{room.id}: '{room.name}' (building: '{room.building}')"
                )
            self.stdout.write(
                self.style.WARNING("Re-run command with --yes to permanently delete these records.")
            )
            return

        # Explicit confirmation passed: delete reservations first (to respect PROTECT), then rooms
        with transaction.atomic():
            hotel_reservations.delete()
            hotel_rooms.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"[Clear Test Data] Successfully deleted {res_count} linked reservation(s) and {room_count} legacy hotel room(s)."
            )
        )

    def seed_demo_data(self, rooms):
        """Creates demo faculty and student accounts with Profile records,
        cleans up any prior [DEMO] reservations, and recreates demo reservations relative to today."""
        # 1. Ensure faculty demo account exists
        faculty_user, f_created = User.objects.get_or_create(
            username='faculty.demo',
            defaults={
                'email': 'faculty.demo@msu.edu.ph',
                'first_name': 'Demo',
                'last_name': 'Faculty',
                'is_staff': False,
                'is_active': True,
            },
        )
        if f_created:
            faculty_user.set_password('Demo@12345')
            faculty_user.save()
            self.stdout.write("[Demo Users] Created demo user 'faculty.demo'.")
        else:
            self.stdout.write("[Demo Users] Demo user 'faculty.demo' already exists.")

        Profile.objects.get_or_create(
            user=faculty_user,
            defaults={
                'user_type': 'faculty',
                'college_department': 'College of Information Technology',
                'contact_number': '09171234567',
            },
        )

        # 2. Ensure student demo account exists
        student_user, s_created = User.objects.get_or_create(
            username='student.demo',
            defaults={
                'email': 'student.demo@msu.edu.ph',
                'first_name': 'Demo',
                'last_name': 'Student',
                'is_staff': False,
                'is_active': True,
            },
        )
        if s_created:
            student_user.set_password('Demo@12345')
            student_user.save()
            self.stdout.write("[Demo Users] Created demo user 'student.demo'.")
        else:
            self.stdout.write("[Demo Users] Demo user 'student.demo' already exists.")

        Profile.objects.get_or_create(
            user=student_user,
            defaults={
                'user_type': 'student',
                'college_department': 'Computer Science Department',
                'contact_number': '09189876543',
            },
        )

        # Retrieve admin user to assign as processed_by for approved/declined requests
        admin_user = User.objects.filter(is_staff=True).first()

        # 3. Clean up prior [DEMO] reservations before creating fresh ones
        old_demo_reservations = Reservation.objects.filter(purpose__startswith='[DEMO]')
        old_count = old_demo_reservations.count()
        if old_count > 0:
            old_demo_reservations.delete()
            self.stdout.write(f"[Demo Reservations] Cleared {old_count} existing [DEMO] reservation(s).")

        # 4. Generate relative dates based on current local date
        today = timezone.localdate()
        yesterday = today - datetime.timedelta(days=1)
        tomorrow = today + datetime.timedelta(days=1)

        # Define approximately 10 demo reservations covering all business requirements:
        # - approved today and tomorrow in different rooms (multiple in CCS Lab 1 for board display)
        # - pending requests
        # - one declined with admin remarks
        # - one cancelled
        # - one approved yesterday (history)
        # - one overlapping pending request created via objects.create (conflict alert test)
        demo_reservations = [
            # --- TODAY: Approved slots in CCS Lab 1 (signature Availability Board timetable) ---
            {
                'room': rooms['CCS Lab 1'],
                'requester': faculty_user,
                'processed_by': admin_user,
                'reservation_date': today,
                'start_time': datetime.time(8, 0),
                'end_time': datetime.time(10, 0),
                'purpose': '[DEMO] Data Structures Hands-on Laboratory',
                'num_attendees': 35,
                'status': 'approved',
                'admin_remarks': 'Approved. Lab assistant on duty.',
            },
            {
                'room': rooms['CCS Lab 1'],
                'requester': student_user,
                'processed_by': admin_user,
                'reservation_date': today,
                'start_time': datetime.time(13, 0),
                'end_time': datetime.time(15, 0),
                'purpose': '[DEMO] Programming Guild Coding Practice',
                'num_attendees': 30,
                'status': 'approved',
                'admin_remarks': 'Approved for accredited student organization.',
            },
            # --- TODAY: Approved slot in Room 201 ---
            {
                'room': rooms['Room 201'],
                'requester': faculty_user,
                'processed_by': admin_user,
                'reservation_date': today,
                'start_time': datetime.time(10, 0),
                'end_time': datetime.time(12, 0),
                'purpose': '[DEMO] CS 101 Lecture on Sorting Algorithms',
                'num_attendees': 45,
                'status': 'approved',
                'admin_remarks': 'Regular class schedule approved.',
            },
            # --- TOMORROW: Approved slots in different rooms ---
            {
                'room': rooms['CCS Lab 1'],
                'requester': faculty_user,
                'processed_by': admin_user,
                'reservation_date': tomorrow,
                'start_time': datetime.time(9, 0),
                'end_time': datetime.time(11, 0),
                'purpose': '[DEMO] Web Application Development Workshop',
                'num_attendees': 38,
                'status': 'approved',
                'admin_remarks': 'Approved. Projector ready.',
            },
            {
                'room': rooms['Conference Room'],
                'requester': faculty_user,
                'processed_by': admin_user,
                'reservation_date': tomorrow,
                'start_time': datetime.time(14, 0),
                'end_time': datetime.time(16, 0),
                'purpose': '[DEMO] Faculty Curriculum Committee Meeting',
                'num_attendees': 18,
                'status': 'approved',
                'admin_remarks': 'Executive room setup confirmed.',
            },
            # --- YESTERDAY: Approved (history) ---
            {
                'room': rooms['Seminar Room'],
                'requester': faculty_user,
                'processed_by': admin_user,
                'reservation_date': yesterday,
                'start_time': datetime.time(14, 0),
                'end_time': datetime.time(16, 0),
                'purpose': '[DEMO] Senior Thesis Defense Presentation',
                'num_attendees': 25,
                'status': 'approved',
                'admin_remarks': 'Defense concluded successfully.',
            },
            # --- TOMORROW: Pending requests ---
            {
                'room': rooms['Lecture Hall 1'],
                'requester': student_user,
                'processed_by': None,
                'reservation_date': tomorrow,
                'start_time': datetime.time(13, 0),
                'end_time': datetime.time(15, 0),
                'purpose': '[DEMO] Student Council General Assembly',
                'num_attendees': 75,
                'status': 'pending',
                'admin_remarks': '',
            },
            {
                'room': rooms['Room 202'],
                'requester': faculty_user,
                'processed_by': None,
                'reservation_date': tomorrow,
                'start_time': datetime.time(10, 0),
                'end_time': datetime.time(12, 0),
                'purpose': '[DEMO] Special Topics in Artificial Intelligence',
                'num_attendees': 40,
                'status': 'pending',
                'admin_remarks': '',
            },
            # --- TOMORROW: Declined with admin remarks ---
            {
                'room': rooms['Engineering Lab'],
                'requester': student_user,
                'processed_by': admin_user,
                'reservation_date': tomorrow,
                'start_time': datetime.time(8, 0),
                'end_time': datetime.time(10, 0),
                'purpose': '[DEMO] Robotics Club Hardware Testing',
                'num_attendees': 20,
                'status': 'declined',
                'admin_remarks': 'Room unavailable due to scheduled hardware maintenance.',
            },
            # --- TOMORROW: Cancelled by user ---
            {
                'room': rooms['CCS Lab 2'],
                'requester': student_user,
                'processed_by': None,
                'reservation_date': tomorrow,
                'start_time': datetime.time(15, 0),
                'end_time': datetime.time(17, 0),
                'purpose': '[DEMO] Peer Tutoring Session',
                'num_attendees': 15,
                'status': 'cancelled',
                'admin_remarks': '',
            },
            # --- TODAY: Overlapping pending request (creates conflict alert against 08:00-10:00 approved) ---
            # Created via objects.create to intentionally bypass clean(), representing the conflict alert case
            {
                'room': rooms['CCS Lab 1'],
                'requester': student_user,
                'processed_by': None,
                'reservation_date': today,
                'start_time': datetime.time(9, 0),
                'end_time': datetime.time(11, 0),
                'purpose': '[DEMO] Overlapping Request - Group Study',
                'num_attendees': 20,
                'status': 'pending',
                'admin_remarks': '',
            },
        ]

        created_res = 0
        for rdata in demo_reservations:
            Reservation.objects.create(
                room=rdata['room'],
                requester=rdata['requester'],
                processed_by=rdata['processed_by'],
                reservation_date=rdata['reservation_date'],
                start_time=rdata['start_time'],
                end_time=rdata['end_time'],
                purpose=rdata['purpose'],
                num_attendees=rdata['num_attendees'],
                status=rdata['status'],
                admin_remarks=rdata['admin_remarks'],
            )
            created_res += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[Demo Reservations] Successfully created {created_res} demo reservations across today, tomorrow, and yesterday."
            )
        )
