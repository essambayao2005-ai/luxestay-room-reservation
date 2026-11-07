# Development Roadmap: MSU-SND Room Checker and Reservation System

> **Document Type:** Project Development Roadmap & Phase 1 Analysis Summary  
> **Source of Truth:** `PROJECT_BRIEF.md` (Updated Version)  
> **Target Platform:** Django 4.2.30, Python 3.12, MariaDB 10.4.32 (XAMPP), Bootstrap 5  
> **Generated Date:** 2026-11-07  

---

## 1. Current State Assessment (Phase 1 Audit)

The following table reports the exact status of the baseline items inspected during Phase 1:

| Item | Inspected Configuration / State | Status | Notes |
|---|---|---|---|
| **Django System Check** | `python manage.py check` executed | **Done** | `System check identified no issues (0 silenced).` |
| **Migrations Dry-Run** | `python manage.py makemigrations --check --dry-run` | **Done** | `No changes detected.` (MariaDB offline during isolated run, schema in sync). |
| **INSTALLED_APPS** | `rooms`, `accounts`, `dashboard` + core Django apps | **Done** | No duplicates found. All three custom apps registered in `luxestay/settings.py`. |
| **TEMPLATES DIRS** | `[BASE_DIR / 'templates']` | **Done** | Correctly configured; `templates/` folder exists at project root. |
| **STATICFILES_DIRS** | `[BASE_DIR / 'static']` | **Done** | Correctly configured; `static/css/` and `static/js/` exist at project root. |
| **MEDIA Settings** | `MEDIA_URL = '/media/'`, `MEDIA_ROOT = BASE_DIR / 'media'` | **Done** | Configured in `settings.py` and routed in `luxestay/urls.py` under `DEBUG`. |
| **LOGIN_URL & Redirects** | `LOGIN_URL = '/accounts/login/'`, `LOGIN_REDIRECT_URL = '/'`, `LOGOUT_REDIRECT_URL = '/'` | **Partly Done** | Base URLs configured. Staff role redirect to `/manage/` must be implemented in login view logic. |
| **TIME_ZONE** | `TIME_ZONE = 'Asia/Manila'`, `USE_TZ = True` | **Done** | Matches campus local time. |
| **Database Settings** | Engine: `django.db.backends.mysql`, DB Name: `luxestay_db` | **Done** | Target is MariaDB 10.4.32 via XAMPP (`127.0.0.1:3306`). Password and secrets exist in config. |
| **Models: `rooms`** | `Room` (`name`, `building`, `room_type`, `capacity`, `description`, `image`, `is_active`) and `Reservation` (`room`, `requester`, `processed_by`, `reservation_date`, `start_time`, `end_time`, `purpose`, `num_attendees`, `status`, `admin_remarks`, timestamps) | **Done** | Models match the brief exactly. `Reservation.clean()` contains conflict and capacity validation. |
| **Models: `accounts`** | `Profile` (`user`, `user_type`, `college_department`, `contact_number`) | **Done** | Matches specification. User type choices: `student` and `faculty`. |
| **Admin Registrations** | `Room` and `Reservation` in `rooms/admin.py`; `Profile` in `accounts/admin.py` | **Done** | All 3 models registered with custom list displays, filters, and search fields. |
| **Templates Directory** | `templates/` at project root | **Partly Done** | Directory exists, but currently empty. Needs `base.html`, partials, and app templates. |
| **Static Directory** | `static/css/` and `static/js/` at project root | **Partly Done** | Directories exist, but currently empty. Needs `style.css` and JS scripts. |
| **MSU Logo Asset** | `msu_logo.png` located in project root | **Partly Done** | File exists at `C:\Projects\luxestay_project\msu_logo.png`; to be copied to `static/img/msu_logo.png` (leaving original in place). |
| **URL Routing** | `luxestay/urls.py` | **Partly Done** | Only `/admin/` and media routes exist. `rooms/urls.py`, `accounts/urls.py`, and `dashboard/urls.py` not yet created. |
| **Dashboard App** | `dashboard/` | **Partly Done** | App created and registered in `INSTALLED_APPS`, but views and routes are empty. |

---

## 2. Legacy System Analysis (`legacy_sirwarz/`)

### 2.1 Overview of Legacy Components
- **`index.html`**: Guest portal with hotel room cards, availability pill, booking modal side-panel, and admin login drawer. Built with gold accents (`#b58d4d`), cream background (`#faf7f2`), and Playfair Display serif fonts.
- **`admin.html`**: Tabbed administration interface with "Rooms Inventory" (room CRUD with file upload) and "Guest Reservations" (Pending and Approved tabs with conflict warnings).
- **`api.php`**: Single monolithic PHP endpoint providing JSON responses for session login, room CRUD, and booking state transitions.
- **`check_room.php`**: Inactive, broken script querying a non-existent `room_status` table.
- **`hotel_db.sql`**: MySQL dump containing tables `rooms`, `bookings`, and `users` (with MD5 hashed passwords).

### 2.2 Ideas Retained
1. **Pending / Approved Workflow**: Reservations submit into a `pending` state awaiting administrator review.
2. **Visual Conflict Alert**: Highlighting pending requests that conflict with already-approved reservations for the same room and time.
3. **Room Image Upload**: Administrative ability to attach room photos with preview.
4. **Pending Count Badges**: Real-time counter on admin navigation indicating pending requests requiring action.

### 2.3 Legacy Elements Dropped
1. **All Hotel Concepts**: Nightly rates, pricing (`PHP`/`₱`), check-in/check-out dates, guest emails/names without user accounts.
2. **PHP Stack**: Dropping `api.php`, `check_room.php`, and PHP session handling completely. Django is the sole backend.
3. **Manual Availability Toggling**: The old system manually set `rooms.is_available = 0` on booking approval and `1` on checkout. The new system computes availability dynamically using SQL subqueries.
4. **Data Purging / Record Deletion**: Legacy code used `DELETE FROM bookings` when rejecting requests or checking out guests. The new system enforces persistent audit history (`declined`, `cancelled` statuses) and `models.PROTECT`.
5. **Old Aesthetic**: Playfair Display fonts, cream/gold palette, and heavy hero imagery are replaced by the clean "Campus Scheduler" design system (Inter font, MSU maroon, champagne accents, warm gray background with refined glassmorphism).

### 2.4 Confirmed Legacy Vulnerabilities & Weaknesses Fixed in Django
- **No CSRF Protection**: Legacy endpoints accepted unverified POST requests. Fixed by Django's `CsrfViewMiddleware` and `{% csrf_token %}`.
- **MD5 Password Storage**: Old system stored weak MD5 hashes. Fixed by Django's PBKDF2 default password hashers.
- **Cross-Site Scripting (XSS)**: Legacy client rendered unsanitized database fields directly into `innerHTML`. Fixed by Django template auto-escaping.
- **Cascading Deletions**: Deleting a room in MySQL cascade-deleted all bookings (`ON DELETE CASCADE`). Fixed by `on_delete=models.PROTECT`.
- **Missing Server-Side Validation**: Dates in the past, inverted check-in/check-out dates, and overlapping approved bookings were insufficiently validated. Fixed by `Reservation.clean()` and Django `ModelForm`.

---

## 3. Comparison with Brief & Key Technical Risks

### 3.1 Django 4.2 with MariaDB 10.4.32 (XAMPP)
- **Constraint**: Must remain on Django 4.2.x (installed: `4.2.30`). Django 5.1+ strictly requires MariaDB 10.5+ and will abort startup on MariaDB 10.4.
- **Operational Rule**: Do not upgrade Django. Ensure XAMPP MySQL service is running on `127.0.0.1:3306` with database `luxestay_db`.

### 3.2 `Reservation.clean()` Pitfalls
- **Unbound Room Instance Pitfall**: If `ReservationForm` excludes `room` and `requester` (because they are set in the view), `form.is_valid()` calls `clean()` on an instance where `self.room_id` is `None`. Consequently, room capacity and overlap checks are silently bypassed.
- **Enforcement Rule**: Always bind `room` and `requester` to the instance prior to calling `form.is_valid()`:
  ```python
  instance = Reservation(room=room, requester=request.user)
  form = ReservationForm(request.POST, instance=instance)
  ```
- **Concurrency & Approval Validation**: When an administrator approves a request in `dashboard:approve`, the approval must re-validate that the request has not lapsed into the past and does not collide with a concurrently approved reservation. This must execute inside `transaction.atomic()`.

### 3.3 Users Without a Profile
- **Scenario**: Superusers or staff created via `python manage.py createsuperuser` or Django Admin do not automatically have a row in `accounts_profile`.
- **Crash Risk**: Calling `request.user.profile.user_type` directly in templates or views will raise `RelatedObjectDoesNotExist`.
- **Enforcement Rule**: Access profiles defensively using `getattr(request.user, 'profile', None)` or `Profile.objects.get_or_create(user=user)`. In UI templates, check `{% if request.user.profile %}` or provide safe fallbacks ("Administrator").

---

## 4. Architecture Confirmation

- **Sole Backend**: Django 4.2.30 (Python 3.12). No PHP code or hybrid PHP/Django bridge exists in the final architecture.
- **Database Engine**: MariaDB 10.4.32 via XAMPP MySQL on `127.0.0.1:3306`, database name `luxestay_db`.
- **Frontend Framework**: Django Templates + Bootstrap 5 (CDN) + Bootstrap Icons (CDN) + Inter Google Font + Vanilla JavaScript. No React, jQuery, or Django REST Framework.
- **Design System**: "Campus Scheduler" styling defined via CSS variables in `static/css/style.css` with primary Maroon (`#641E2B`), Warm Gray (`#F5F3F0`), Champagne (`#E9DDC8`), and Charcoal (`#5F6368`), paired with the defined Glass Recipe (ambient blurred floating shapes, glass cards with `backdrop-filter`, and near-solid white inputs/cells for WCAG AA readability).

---

## 5. Seven-Phase Development Roadmap

The roadmap organizes the project into 7 structured phases, mapping the Brief's Phase A to Phase 3, Phases B–D to Phase 4, and Phase E to Phases 5–7.

```
┌────────────────────────────────────────────────────────┐
│ Phase 1: Analysis and Planning (Done)                  │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 2: Database and Backend Preparation              │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 3: UI/UX and Frontend (Brief Phase A)            │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 4: System Features (Brief Phases B, C, D)        │
│   4.1 Accounts & Authentication (Phase B)              │
│   4.2 Requester Reservations (Phase C)                 │
│   4.3 Staff Management Dashboard (Phase D)             │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 5: Integration (Brief Phase E - Part 1)          │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 6: Testing and Debugging (Brief Phase E - Part 2)│
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 7: Finalization & Handover (Brief Phase E - Part 3│
└────────────────────────────────────────────────────────┘
```

---

### Phase 1: Analysis and Planning
- **Status:** **Completed**
- **Tasks Completed:**
  - Audited Django configuration, settings, migrations, and installed apps.
  - Verified `rooms_room`, `rooms_reservation`, and `accounts_profile` schemas.
  - Inspected `legacy_sirwarz/` code, identified keep/drop items, and documented legacy flaws.
  - Documented MariaDB 10.4 compatibility rules, `Reservation.clean()` pitfalls, and missing Profile edge cases.
- **Deliverable:** `DEVELOPMENT_ROADMAP.md` created.

---

### Phase 2: Database and Backend Preparation
- **Objective:** Ensure database connectivity, migration stability, URL routing structures, and initial sample data seeding.
- **Dependencies:** Phase 1 completion, local XAMPP MySQL service active.

#### Tasks:
1. **Task 2.1: Verify MariaDB Connectivity & Migration Application**
   - *Dependencies:* XAMPP MySQL running with database `luxestay_db`.
   - *Action:* Run `python manage.py showmigrations` and `python manage.py migrate` to guarantee all tables are created in MySQL.
   - *Expected Result:* All migrations (`0001_initial` through `0003_reservation` in `rooms`, `0001_initial` in `accounts`) marked applied `[X]`.
2. **Task 2.2: Establish URL Routing Skeleton with Namespaces**
   - *Dependencies:* Task 2.1.
   - *Action:* Create `rooms/urls.py`, `accounts/urls.py`, and `dashboard/urls.py` with `app_name` namespaces (`rooms`, `accounts`, `dashboard`). Include them in `luxestay/urls.py`.
   - *Expected Result:* URL reversing works (`reverse('rooms:room_list')`, `reverse('accounts:login')`, `reverse('dashboard:home')`).
3. **Task 2.3: Asset Organization (`msu_logo.png`)**
   - *Dependencies:* None.
   - *Action:* Create `static/img/` directory and copy `msu_logo.png` to `static/img/msu_logo.png` (retaining the root original).
   - *Expected Result:* Logo is available at `static/img/msu_logo.png` for templates, app shell, and favicon.
4. **Task 2.4: Implement `seed_rooms` Management Command**
   - *Dependencies:* Task 2.1.
   - *Action:* Create `rooms/management/commands/seed_rooms.py` to seed 6 realistic campus rooms across different buildings (e.g. Science Hall, Engineering Building, Administration Complex) and sample approved reservations for today and tomorrow.
   - *Expected Result:* Executing `python manage.py seed_rooms` populates the database idempotently with test rooms and reservations.

---

### Phase 3: UI/UX and Frontend (Brief Phase A: App Shell & Public Pages)
- **Objective:** Construct the complete "Campus Scheduler" design system with the frosted glass recipe, app shell layout, public room catalog, and signature Availability Board.
- **Dependencies:** Phase 2.

#### Tasks:
1. **Task 3.1: Design System CSS & Glass Recipe Implementation**
   - *Dependencies:* Task 2.3.
   - *Action:* Create `static/css/style.css` defining:
     - `:root` color tokens (`--maroon`, `--white`, `--warm-gray`, `--charcoal`, `--champagne`, `--maroon-dark`, `--maroon-tint`, `--ink`, `--border`).
     - Typography (Inter, tabular figures for times/dates).
     - **Glass Recipe:** ambient floating blurred shapes in background (`filter: blur(80px)`), frosted glass surfaces (`background: rgba(255,255,255,.68)`, `backdrop-filter: blur(16px) saturate(120%)`, border, and soft shadow), maroon glass sidebar (`rgba(100,30,43,.94)`), solid readability backgrounds (`rgba(255,255,255,.92)`) for inputs and tables, and `@supports not (backdrop-filter)` fallback.
     - Shape radiuses (cards 16–24px, buttons/inputs 12px) and motion transitions (180–250ms with `prefers-reduced-motion` check).
   - *Expected Result:* Comprehensive CSS theme matching Section 9 of the brief.
2. **Task 3.2: Base Template & App Shell (`base.html` and Partials)**
   - *Dependencies:* Task 3.1.
   - *Action:* Create `templates/base.html`, `templates/partials/sidebar.html`, `templates/partials/topbar.html`, and `templates/partials/messages.html`. Implement 260px fixed maroon glass sidebar with `msu_logo.png` (48–56px, un-stretched on a white chip if needed), active link indicator (3px champagne bar), mobile offcanvas menu, and user chip.
   - *Expected Result:* Unified responsive app shell rendering properly from 360px up to widescreen desktop with AA contrast.
3. **Task 3.3: Public Room List & Filter View (Cards View)**
   - *Dependencies:* Task 3.2.
   - *Action:* Implement `rooms:room_list` view (`templates/rooms/room_list.html`) with filter form (date, start time, end time, building dropdown, min capacity). Display rooms as glass cards with thumbnail/initials, capacity, and computed status badge ("Available", "Occupied", "In use until...").
   - *Expected Result:* Filtering dynamically checks approved reservations via SQL `Exists` subquery without Python loops.
4. **Task 3.4: Signature Availability Board View**
   - *Dependencies:* Task 3.3.
   - *Action:* Implement timetable view (server-rendered CSS grid, hours `BOARD_START_HOUR=7` to `BOARD_END_HOUR=21`). Draw approved reservations as styled blocks with tooltips (anonymous for visitors). Add previous/next day buttons, Today button, date picker, and vertical red/maroon "now" indicator line on current day.
   - *Expected Result:* Toggle switch smoothly alternates between Cards View and Availability Board with consistent query performance (single query per day).

---

### Phase 4: System Features (Brief Phases B, C, D)

#### 4.1 Accounts & Authentication (Brief Phase B)
- **Objective:** Requester registration, login/logout, and role-based routing.
- **Dependencies:** Phase 3.
- **Tasks:**
  1. *Registration Form & View (`accounts:register`):* Create `UserRegistrationForm` combining `User` fields and `Profile` fields (`user_type`, `college_department`, `contact_number`). Handle atomic creation in `accounts/views.py`.
  2. *Split-Screen Auth Templates:* Create `templates/accounts/login.html` and `templates/accounts/register.html` with maroon left-brand panel containing large `msu_logo.png` (96–120px) and university name; right panel with centered glass card form.
  3. *Role-Based Login Redirects:* Customize `LoginView` to redirect staff (`is_staff=True`) to `/manage/` and regular requesters to `/` (or `?next=`).
  4. *Profile Defense Guard:* Wrap all profile accesses with fallbacks to avoid crashes when superusers lack a `Profile` instance.
- **Expected Result:** New users can register, log in, and log out (via POST); role redirects function correctly.

#### 4.2 Requester Reservations (Brief Phase C)
- **Objective:** Reservation booking flow, conflict prevention, and self-service reservation management.
- **Dependencies:** Phase 4.1.
- **Tasks:**
  1. *Reservation Form with Instance Pre-binding (`rooms:reservation_create`):* Create `ReservationForm` in `rooms/forms.py`. Bind `room` and `requester` prior to validation. Ensure `Reservation.clean()` runs cleanly and surfaces inline errors.
  2. *Availability Board Slot Click Integration:* Allow clicking an empty board cell to open `/reserve/<room_id>/?date=YYYY-MM-DD&start=HH:MM` with fields prefilled.
  3. *My Reservations Table (`rooms:my_reservations`):* Create requester reservations table showing status pills, purpose, date/time, and administrator remarks.
  4. *Pending Edit & Cancel Flows:* Create `rooms:reservation_edit` (only accessible if `status == 'pending'`) and `rooms:reservation_cancel` (POST confirmation modal, transitions status to `cancelled`). Return 404 for unowned reservations.
- **Expected Result:** Requesters can reserve rooms, receive real-time conflict feedback, and manage their own pending bookings.

#### 4.3 Staff Management Dashboard (Brief Phase D)
- **Objective:** Complete administrative control center for reservations, rooms, users, and reports.
- **Dependencies:** Phase 4.2.
- **Tasks:**
  1. *Staff Security Decorator:* Create `@staff_required` decorator redirecting or rejecting non-staff users with 403.
  2. *Dashboard Home (`dashboard:home`):* Build stat cards (Pending Requests, Approved Today, Active Rooms, Registered Users) with vanilla JS count-up animation, today's schedule, and pending request quick actions.
  3. *Reservations Management (`dashboard:reservation_list`):* Tabbed interface (Pending, Approved, History). Add Approve and Decline action endpoints (`dashboard:approve`, `dashboard:decline` with remarks modal). Display warning alert on pending requests that conflict with approved bookings.
  4. *Concurrency Guard on Approve:* Wrap approval logic in `transaction.atomic()`, re-running overlap check and verifying reservation date/time is not in the past.
  5. *Room CRUD (`dashboard:room_*`):* List, add, edit with image upload (validate image type, max 2MB), and delete. If room has existing reservations, block deletion (`models.PROTECT`) and prompt deactivation (`is_active=False`).
  6. *User Management (`dashboard:user_*`):* List users, display user type and college/department, toggle active/inactive status, and handle protected deletion.
  7. *Printable Reports (`dashboard:reports`):* Date, room, requester, and status filters with clean print stylesheet (`@media print` hiding sidebar and top bar, placing `msu_logo.png` at report header).
- **Expected Result:** Administrators have complete oversight over campus room scheduling with zero legacy dependencies.

---

### Phase 5: Integration (Brief Phase E - Part 1)
- **Objective:** Unify navigation, error handling, access control, and dynamic state synchronization across all modules.
- **Dependencies:** Phase 4.

#### Tasks:
1. **Task 5.1: Navigation Bar & Badge Synchronization**
   - *Dependencies:* Tasks 4.1, 4.3.
   - *Action:* Synchronize sidebar items by role (Visitor, Requester, Admin). Display dynamic pending reservation count badge in staff sidebar.
   - *Expected Result:* Sidebar correctly highlights current route with champagne marker and displays accurate pending counts.
2. **Task 5.2: Custom Error Handlers (404 and 403)**
   - *Dependencies:* Phase 3.
   - *Action:* Create `templates/404.html` and `templates/403.html` matching the glass "Campus Scheduler" theme.
   - *Expected Result:* Friendly, accessible error pages that prevent default raw Django tracebacks.
3. **Task 5.3: End-to-End User Journey Verification**
   - *Dependencies:* Tasks 4.1–4.3.
   - *Action:* Verify complete lifecycle: Visitor checks board -> registers/logs in -> reserves room -> Admin sees conflict badge -> Admin approves -> Room shows occupied on public board -> Requester sees updated status.
   - *Expected Result:* Flawless state propagation with zero query leaks or UI glitches.

---

### Phase 6: Testing and Debugging (Brief Phase E - Part 2)
- **Objective:** Automated test coverage, edge-case hardening, and responsive cross-device verification.
- **Dependencies:** Phase 5.

#### Tasks:
1. **Task 6.1: Automated Unit & Business Logic Tests**
   - *Dependencies:* Phase 4.
   - *Action:* Create tests in `rooms/tests.py` covering:
     - Back-to-back booking permission (allowed).
     - Overlapping approved booking rejection in `clean()`.
     - Submitting/editing pending reservations in the past (rejected).
     - Over-capacity booking rejection.
     - Unbound model form validation safety.
     - Status transition validation (pending -> approved/declined/cancelled).
   - *Expected Result:* `python manage.py test` passes with 100% success.
2. **Task 6.2: Security & Permissions Tests**
   - *Dependencies:* Task 6.1.
   - *Action:* Create tests in `accounts/tests.py` verifying non-staff cannot access `/manage/`, requesters cannot view or cancel other users' reservations, and CSRF is enforced.
   - *Expected Result:* All permission guards verified.
3. **Task 6.3: Responsive & Cross-Browser Polish**
   - *Dependencies:* Task 5.1.
   - *Action:* Audit layout on 360px mobile viewports (offcanvas sidebar, board horizontal scroll, touch targets >= 40px, WCAG AA color contrast, glass fallback test).
   - *Expected Result:* Fluid UI responsiveness without horizontal overflow or clipped text.

---

### Phase 7: Finalization & Handover (Brief Phase E - Part 3)
- **Objective:** Final documentation, clean package specifications, and student defense presentation script.
- **Dependencies:** Phase 6.

#### Tasks:
1. **Task 7.1: Pagination & Query Optimization**
   - *Dependencies:* Phase 5.
   - *Action:* Add Django pagination (10 per page) to long list views (My Reservations, Admin Reservations, Users). Add `select_related('room', 'requester')` to prevent N+1 template queries.
   - *Expected Result:* Fast response times and clean pagination controls.
2. **Task 7.2: Update Requirements & Project Documentation (`README.md`)**
   - *Dependencies:* Task 7.1.
   - *Action:* Update `README.md` with complete setup instructions from `git clone`, venv activation, `requirements.txt` installation, XAMPP MariaDB setup, migrations, `seed_rooms`, and `runserver`. Include notes on development credentials.
   - *Expected Result:* A clean, new developer can set up the project from scratch in under 5 minutes.
3. **Task 7.3: Defense Demo Script (FR-01 to FR-09)**
   - *Dependencies:* Task 7.2.
   - *Action:* Provide a structured 5-minute presentation script demonstrating each functional requirement (FR-01 to FR-09) sequentially for the students' oral defense.
   - *Expected Result:* Ready-to-rehearse defense walkthrough script.

---

## 6. Open Questions for the Students

Before proceeding with code implementation in Phase 2, please confirm:

1. **Campus-Specific Room Names for `seed_rooms`**:
   - Do you have specific building names or classroom numbers you would like the sample database to contain (e.g. *College of Engineering Rm 101*, *CS Lab 2*, *Main Auditorium*), or should we use standard campus building names?
2. **Local XAMPP Service Check**:
   - Please confirm that Apache and MySQL services are started in your XAMPP Control Panel and that the database `luxestay_db` exists before we execute database commands in Phase 2.
3. **Superuser Profile Handling**:
   - When superusers (such as `admin1`) are created via `createsuperuser`, they have no `Profile` record. We will configure the system to handle this gracefully (displaying "Administrator" and safe defaults). Should the admin dashboard also allow superusers to attach a campus department to their account later?
