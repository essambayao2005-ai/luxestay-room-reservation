# PROJECT BRIEF: Room Checker and Reservation System (Django)

Read this whole file before writing any code. It is the single source of truth for this project.
If something here conflicts with your own ideas, follow this file. If something is unclear, ask first.

---

## 1. What we are building

A web system for a **school campus** where students, student organization officers, and faculty can
**check which rooms are free** and **reserve a room for a date and time**, and where an
**administrator** approves or declines the requests. Room use is **free** (no prices, no payment).

This is the 4th-year version of our 3rd-year PHP system. We are **converting** it to Django, not
creating an unrelated system. The old code is in `legacy_sirwarz/` (reference only, see section 4).

Users:
- **Visitor** (not logged in): can browse rooms and check availability. Cannot reserve.
- **Requester** (registered user: student / student org officer / faculty): everything a visitor can do,
  plus reserve rooms and manage own reservations. Student and faculty have the SAME permissions.
- **Administrator** (`is_staff = True`): manages reservations, rooms, users, and reports.

## 2. Hard constraints (do not break these)

- **Python 3.12, Django 4.2.x** (4.2.30 installed). Do not upgrade Django. The database is
  **MariaDB 10.4.32 (XAMPP)**, which Django 5.1+ does not support.
- **Database:** MySQL/MariaDB, database name `luxestay_db`, user `root`, empty password, host `127.0.0.1`.
  Already configured in `luxestay/settings.py`. Do not switch to SQLite.
- **Allowed packages only:** `django`, `mysqlclient`, `pillow` (see `requirements.txt`).
  Do NOT add other Python packages. **Bootstrap 5**, the **Inter** font (Google Fonts), and **Bootstrap Icons**
  come from CDN `<link>`/`<script>` tags in `base.html`. No other CDNs. Small interactions use plain
  vanilla JavaScript in `static/js/`. No React, no jQuery, no Django REST Framework.
- **No PHP** in the final system. No hotel wording, prices, nights, check-in/check-out, or hotel photos.
- Keep code **simple and readable**. Students must be able to explain every file at their defense.
  Use Django built-ins (generic views, ModelForm, `login_required`, messages framework) before custom code.
- Every model class, view, and non-obvious function needs a short comment explaining WHY it exists.
- Do not touch `legacy_sirwarz/`. Do not commit `venv/`, `media/`, or `legacy_sirwarz/` (already in `.gitignore`).

## 3. Current state (already done by the students)

- Django project `luxestay` created, connected to MySQL, `migrate` works.
- App `rooms` with model **Room**, registered in admin.
- Apps `accounts` (model **Profile**) and `dashboard` (empty) created.
- Model **Reservation** (in `rooms/models.py`) with conflict validation in `clean()`.
- `templates/` and `static/css/`, `static/js/` folders exist and are configured in settings.
- The MSU-SND logo already exists as `msu_logo.png` in the project folder (see section 9 for how to use it).
- A superuser exists (`admin1`). Git repo is pushed to GitHub: `essambayao2005-ai/luxestay-room-reservation`.

**Before writing any code, verify this state and report the result:**
1. `python manage.py check` shows no issues.
2. `python manage.py makemigrations --check` reports no pending changes.
3. `rooms/models.py` contains `Room` and `Reservation`; `accounts/models.py` contains `Profile`.
4. The Django admin (`/admin/`) lists Rooms, Reservations, and Profiles.

If any of this is missing, tell the students instead of inventing it.

## 4. Old system reference (`legacy_sirwarz/`)

| Old file | What it did | In Django |
|---|---|---|
| `index.html` | Guest page: room cards, Available/Fully Booked badge, booking side panel, admin login side panel | `templates/rooms/room_list.html` + login page |
| `admin.html` | Admin: Rooms Inventory tab (CRUD with image upload), Guest Reservations tab (Pending/Approved) | `dashboard` app pages |
| `api.php` | All backend logic and JSON API | Django views (no JSON API needed) |
| `check_room.php` | Broken, unused | Delete idea, do not port |
| `hotel_db.sql` | Old tables `rooms`, `bookings`, `users` | Replaced by the models in section 6 |

Copy only the **ideas** (pending/approved tabs, conflict alert, image upload). Do NOT copy the old code and do NOT
copy the old look (cream background, gold accent, serif headings, top tab bar): the new design is completely
different and is defined in section 9. Known weaknesses of the old system that the new one must fix:
manual on/off availability flag; deleted records instead of statuses; unescaped HTML (XSS); MD5 passwords;
no server-side validation; no CSRF; room delete cascaded to bookings.

## 5. Target structure

```
luxestay_project/
  manage.py, requirements.txt, PROJECT_BRIEF.md, README.md
  luxestay/            settings.py, urls.py
  rooms/               models.py (Room, Reservation), views.py, forms.py, urls.py, admin.py
  accounts/            models.py (Profile), views.py, forms.py, urls.py, admin.py
  dashboard/           views.py, forms.py, urls.py   (custom admin module, no models)
  templates/           base.html, partials/ (sidebar, topbar, messages), rooms/, accounts/, dashboard/
  static/css/style.css, static/js/, static/img/msu_logo.png   (copy of the existing msu_logo.png from the project folder)
```

URL map (use URL namespaces):

| URL | Name | Who | Purpose |
|---|---|---|---|
| `/` | `rooms:room_list` | everyone | Room list + availability search |
| `/reserve/<room_id>/` | `rooms:reservation_create` | login | Reservation form |
| `/my-reservations/` | `rooms:my_reservations` | login | Own reservations, status, remarks |
| `/my-reservations/<pk>/edit/` | `rooms:reservation_edit` | owner, pending only | Edit |
| `/my-reservations/<pk>/cancel/` | `rooms:reservation_cancel` | owner, pending only, POST | Cancel |
| `/accounts/register/` | `accounts:register` | visitor | Create account + profile |
| `/accounts/login/`, `/accounts/logout/` | `accounts:login`, `accounts:logout` | all | Auth (logout via POST) |
| `/manage/` | `dashboard:home` | staff | Summary cards + pending list |
| `/manage/reservations/` | `dashboard:reservation_list` | staff | Tabs: Pending, Approved, History |
| `/manage/reservations/<pk>/approve/` | `dashboard:approve` | staff, POST | Approve |
| `/manage/reservations/<pk>/decline/` | `dashboard:decline` | staff, POST | Decline with remarks |
| `/manage/rooms/` (+ `add/`, `<pk>/edit/`, `<pk>/delete/`) | `dashboard:room_*` | staff | Room CRUD with image upload |
| `/manage/users/` (+ toggle active, delete) | `dashboard:user_*` | staff | Manage users |
| `/manage/reports/` | `dashboard:reports` | staff | Filter history and print |
| `/admin/` | Django admin | superuser | Developer tool only, not part of the user-facing system |

`LOGIN_URL = '/accounts/login/'`. After login: staff go to `/manage/`, everyone else to `/`.
All `/manage/` pages require `is_staff`; non-staff get a 403 page or a redirect with a message.

## 6. Data model (FINAL, field names must match exactly, they are in our printed documents)

**Room** (`rooms_room`): `name` (100), `building` (100), `room_type` (choices: lecture, laboratory,
conference), `capacity` (positive int), `description` (text, blank), `image` (ImageField, `upload_to='rooms/'`,
optional), `is_active` (bool, default True). No price field.

**Reservation** (`rooms_reservation`): `room` (FK Room, PROTECT), `requester` (FK User, PROTECT),
`processed_by` (FK User, null, SET_NULL), `reservation_date`, `start_time`, `end_time`, `purpose` (255),
`num_attendees` (positive int), `status` (pending / approved / declined / cancelled, default pending),
`admin_remarks` (255, blank), `created_at`, `updated_at`.

**Profile** (`accounts_profile`): `user` (OneToOne User), `user_type` (student / faculty), `college_department`
(100), `contact_number` (20).

**User**: Django's built-in `auth_user`. Administrator = `is_staff`.

Do not add, rename, or remove fields without asking. If you believe a change is needed, explain why and wait.

## 7. Business rules

1. **Availability is computed, never stored.** A room is *Occupied* for a date and time range if an
   **approved** reservation for the same room and date overlaps it. Overlap rule:
   `existing.start_time < new_end AND existing.end_time > new_start` (back-to-back bookings are allowed).
   Only `is_active=True` rooms are shown to requesters. Use an `Exists` subquery for the search
   (do not loop over rooms in Python).
2. Reservation validation (already in `Reservation.clean()`, reuse it through a ModelForm):
   end time after start time; date not in the past (when creating, and while the status is pending,
   so editing a pending request into the past is refused); attendees <= room capacity;
   no overlap with an approved reservation (for pending/approved statuses).
   **Pitfall:** if the form does not include `room` and `requester` (they are fixed by the view), set them on
   the instance BEFORE validation, e.g. `form = ReservationForm(request.POST, instance=Reservation(room=room,
   requester=request.user))`. If `room` is not set when `clean()` runs, the overlap and capacity checks are
   silently skipped. Test this explicitly.
3. Status flow: `pending` -> `approved` or `declined` (by admin) ; `pending` -> `cancelled` (by owner).
   No other transitions. Approved/declined/cancelled records are never deleted (history).
4. Approving re-runs the overlap check; if it fails, show an error and do not approve. Approving a
   request whose date and time are already in the past is refused. Declining requires `admin_remarks`.
   Set `processed_by` to the admin who acted. Do the check and the save inside `transaction.atomic()`
   so two admins cannot approve overlapping requests at the same moment.
5. A pending request that overlaps an approved one shows a **conflict alert** in the admin list.
6. A requester can only see and change their own reservations (check ownership in every view).
7. A room that has reservations cannot be deleted (PROTECT); show a friendly message and suggest
   deactivating it (`is_active=False`). A user with reservations cannot be deleted; offer deactivate.
8. "Notifications" = the status and remarks shown in My Reservations (no email, no SMS).
9. Registering creates the User and the Profile together (one transaction).
10. Users created outside the register page (for example `admin1` in Django admin) may have no Profile.
    Never assume `user.profile` exists; use `getattr(user, 'profile', None)` or `get_or_create`.

## 8. Pages and behavior (map to our documented requirements)

**Requester side**
- **Room list / availability (FR-02):** form with date, start time, end time, building (dropdown of
  existing buildings + "All"), minimum capacity. With no search, list all active rooms. With a search, show each
  room as Available or Occupied for that slot; Available rooms have a **Reserve** button (link to login first
  if not logged in, then return to the room via `?next=`). The page has two views of the same data, switched
  with a toggle: **Cards** and the **Availability Board** (see section 9, this is the signature feature).
- **Register / Login (FR-01):** register form = username, first name, last name, email, user type, college or
  department, contact number, password twice. Use Django's `AuthenticationForm` and `LoginView`.
- **Reservation form (FR-03, FR-04):** room is shown read-only; fields date, start, end, purpose, attendees.
  Validation errors from `clean()` appear on the form. Success -> message + redirect to My Reservations.
- **My Reservations (FR-06, FR-08):** table with room, date, time, purpose, status badge, admin remarks;
  Edit and Cancel buttons only on pending ones (Cancel asks for confirmation and uses POST).

**Administrator side (custom module, same app shell and design as the rest of the system)**
- **Dashboard:** cards = pending requests, approved today, active rooms, registered users; plus the pending list.
- **Reservations (FR-05):** tabs Pending / Approved / History (all). Pending rows: Approve and Decline
  (decline opens a small form for remarks). Show conflict alerts.
- **Rooms (FR-07):** table + add/edit form with image upload (accept jpg, jpeg, png, webp; max 2 MB; validate
  content type), delete with the protection rule in section 7.
- **Users (FR-07):** list with type and college, deactivate/activate, delete when allowed.
- **Reports (FR-09):** filters (date range, room, requester, status), results table, **Print** button
  (a print stylesheet that hides the navigation and buttons, removes glass/blur effects for clean printing, and
  shows the MSU-SND logo, the full university name, the report title, the filters used, and the date at the top).
  CSV export is optional, do it last.

## 9. Design system: "Soft Glass Campus" (Soft Glassmorphism + Modern Minimalist, a NEW look)

**Goal:** apply a **Soft Glassmorphism + Modern Minimalist** style to the whole system: smooth rounded corners,
subtle transparency and background blur, soft shadows, and clean spacing. It must feel **smooth, refined,
welcoming, and professional**, like a modern campus scheduling app. It must NOT feel edgy, sharp, over-futuristic,
or like a hotel or booking website. Keep a few real "wow" moments.
**Do not use:** gold, cream backgrounds, serif fonts, hero photographs, hotel imagery or wording, neon or glowing
effects, hard-edged or rainbow gradients, heavy blur, dark "cyber" themes, or thick dark shadows.

**Campus identity (required, consistent everywhere):** the official name is **MSU-SND (Mindanao State University
– Sultan Naga Dimaporo)**. Show the logo (see "Logo" below) and the name on the login and register pages, the sidebar,
the top bar on phones, the footer, the error pages, the browser tab (`<title>`: "MSU-SND Room Reservation"), and
at the top of every **printed report** (logo + full university name + report title + date).

**Color tokens** (define as CSS variables in `:root`; the first five are fixed by the students):

| Token | Value | Use |
|---|---|---|
| `--maroon` | `#641E2B` | Sidebar, primary buttons, active navigation (and nothing else big) |
| `--white` | `#FFFFFF` | Main surfaces: cards, tables, forms |
| `--warm-gray` | `#F5F3F0` | App background, subtle sections, table headers |
| `--charcoal` | `#5F6368` | Secondary text and icons |
| `--champagne` | `#E9DDC8` | Small accents only: active-item bar, icon chips, badges, today marker, dividers |
| `--maroon-dark` | `#4E1722` | Hover/pressed state of maroon (derived) |
| `--maroon-tint` | `rgba(100,30,43,.08)` | Hover rows, selected items, reserved blocks (derived) |
| `--ink` | `#1F2023` | Primary text (derived dark neutral) |
| `--border` | `#E7E2DB` | 1px borders and dividers (derived) |

Status pills (soft background, dark text): Available/Approved `#2F6B4A` on `#E6F1EA`; Occupied/Declined
`#641E2B` on `#F4E6E8`; Pending `#7A5A1E` on `#E9DDC8`; Cancelled `#5F6368` on `#ECEAE6`;
Conflict `#8A5A00` on `#FFF3D6`.

**Typography:** **Inter** only (400, 500, 600, 700). H1 28px/700, H2 22px/600, body 15px/400, small 13px.
Headings with slight negative letter-spacing (-0.01em). Use `font-variant-numeric: tabular-nums` for times,
counts, and dates.

**Shape and depth:** cards and panels radius 16 to 24px; buttons and inputs radius 12px; 8px spacing grid; roomy
padding (24px in cards). Icons: Bootstrap Icons, drawn in `--charcoal` (maroon when active).

**Glass recipe** (define once as CSS variables or a `.glass` class and reuse it; do not invent variations):
- **Page background:** `--warm-gray` as the base, with two or three very large decorative shapes behind the
  content (fixed position, `pointer-events: none`): champagne `#E9DDC8` and maroon at 8 to 12% opacity, softly blurred
  (`filter: blur(80px)`), drifting very slowly (20 to 30 s loop, transform only). No images.
- **Glass surface** (top bar, cards, stat cards, search panel, availability board container, modals, dropdowns,
  the login card): `background: rgba(255,255,255,.68)`; `backdrop-filter: blur(16px) saturate(120%)`;
  `border: 1px solid rgba(255,255,255,.65)`; `box-shadow: 0 8px 32px rgba(100,30,43,.08)`; a soft inner highlight
  (`inset 0 1px 0 rgba(255,255,255,.7)`).
- **Maroon sidebar:** `rgba(100,30,43,.94)` with `backdrop-filter: blur(12px)`, almost opaque so white text stays crisp.
- **Keep it readable:** form inputs, table body cells, and long text sit on near-solid white
  (`rgba(255,255,255,.92)`). Text on glass uses `--ink` or `--charcoal`; maintain WCAG AA contrast.
- **Fallback:** `@supports not (backdrop-filter: blur(1px))` uses `rgba(255,255,255,.96)` with no blur.
- **Performance:** at most one blur layer per screen region, never nest `backdrop-filter`, no blur on every table
  row, and animate only `transform` and `opacity`. It must feel smooth on an ordinary school laptop.

**App shell (same for all roles, this is what makes it feel like an app):**
- Fixed **maroon glass sidebar** (260px): logo + "MSU-SND" + small caption "Room Checker and Reservation System";
  nav items with icons; the **active item** has white text, a slightly darker maroon background, and a 3px
  **champagne bar** on the left; at the bottom a user chip (initials in a champagne circle, name, role) and Sign out.
- Content area on `--warm-gray` with a slim top bar (page title and today's date as a champagne chip).
- On phones the sidebar becomes an offcanvas menu opened from a hamburger in the top bar.
- Sidebar items: **Visitor:** Rooms, Availability Board, Sign in, Register. **Requester:** Rooms,
  Availability Board, My Reservations, Profile. **Admin:** Dashboard, Reservations (with a pending-count badge),
  Rooms, Users, Reports.
- **Login and Register:** split screen. Left half maroon with the logo (on a white chip if needed), "MSU-SND",
  the full university name, the system name, and a one-line tagline; right half shows the form in a centered glass
  card over the soft blurred background.
- **Logo:** use the **existing `msu_logo.png`** that is already in the project folder. Find it first (search the
  project, it may be in the project root). Copy it to `static/img/msu_logo.png` (leave the original in place) and load
  it with `{% static 'img/msu_logo.png' %}`. Show it: in the **sidebar** header (about 48 to 56px), on the **login and
  register** pages (large, about 96 to 120px), in the **top bar** on phones (about 32px), in the footer, on the
  error pages, as the **favicon**, and at the top of printed reports.
  **Preserve the logo exactly:** do not recolor, filter, crop, recolor-on-hover, stretch, or add effects. Set only
  the width or the height and keep `height: auto` / `object-fit: contain` so the proportions stay the same. If the
  logo needs more contrast on a maroon background, place it unchanged on a white rounded or circular chip.

**Signature feature: the Availability Board** (the "wow", also the heart of a *room checker*):
- A day timetable: **rows = rooms** (grouped by building), **columns = hours** (display range from settings
  `BOARD_START_HOUR = 7` to `BOARD_END_HOUR = 21`; this is only a display setting, not a booking rule).
- Approved reservations are drawn as blocks (`--maroon-tint` background, 3px maroon left border) at their exact
  time span, with a tooltip (time and purpose). Visitors and other requesters see only "Reserved" (no names);
  admins also see the requester.
- On today's date, a thin vertical **"now" line** marks the current time and the label chip is champagne.
- Date navigation: previous/next day arrows, a date picker, and a **Today** button. Respects the building filter.
- Hovering a free cell shows a "+"; clicking it opens the reservation form with the room, date, and start time
  prefilled (login required, same `?next=` flow).
- Build it server-side with CSS grid (no chart library). Blocks fade/scale in with a short stagger.

**Room cards (Cards view):** white cards, no large photos: a small rounded thumbnail (or a champagne square with
the room's initials), name, building chip (champagne), room type, capacity with a people icon, a status pill for the
searched slot, a line such as **"Free now"** (green dot) or **"In use until 3:00 PM"** computed from approved
reservations for the current time, and a maroon **Reserve** button.

**Admin dashboard:** four stat cards (champagne icon chip, big number, label) with a **count-up** animation,
a "Today's schedule" list, and the newest pending requests with Approve/Decline buttons. Tables: white, warm-gray
header row, subtle row hover with `--maroon-tint`, sticky header on long lists.

**Motion (smooth, subtle):** 180 to 250 ms `ease-out`; animate only `transform` and `opacity`; page content
fades in (200 ms); cards lift 2px on hover; buttons have pressed feedback; Bootstrap toasts or messages slide in;
the offcanvas sidebar slides; stat numbers count up (about 600 ms, vanilla JS). Wrap all animations so that
`prefers-reduced-motion: reduce` disables them.

**Quality of finish:** consistent spacing, no layout jumps, empty states with an icon and a helpful sentence,
friendly 404 and 403 pages in the same style, WCAG AA contrast (charcoal `#5F6368` is only for secondary text),
a visible focus ring (2px maroon with a champagne offset), buttons and inputs at least 40px tall,
fully responsive from 360px wide.

Use the Bootstrap 5 grid, forms, tables, offcanvas, and toasts as the base, then restyle them with the tokens above
in `static/css/style.css` (override Bootstrap variables where possible instead of writing many one-off rules).

## 10. Security and quality checklist (must pass before the final commit)

- CSRF token on every POST form. All destructive actions use POST, never GET.
- Auto-escaped templates only; never use `|safe` or `mark_safe` on user input.
- `login_required` on requester pages; `is_staff` check on every `/manage/` view (use one reusable decorator or mixin).
- Ownership check on edit/cancel. Return 404 (not 403) for other people's reservations.
- Passwords use Django's default hashers and validators.
- Server-side validation for all rules in section 7 (never rely on browser validation).
- `messages` framework for success and error feedback. Friendly 404 and 403 pages.
- `DEBUG`, `SECRET_KEY`, and DB password may stay as-is for local use, but note it in the README.
- No query inside a loop in templates (use `select_related('room', 'requester')`). Build the Availability Board
  with one query per page (fetch the day's approved reservations once, then group them in Python).
- Visitors and other requesters must never see names or purposes of other people's reservations (board and cards).

## 11. Phases (stop after each phase, run it, let the students test and commit)

**Phase A: App shell and public pages.** `base.html` (Bootstrap 5, Inter, Bootstrap Icons via CDN, maroon sidebar,
top bar, messages), `static/css/style.css` with all design tokens from section 9, the room list page with the
availability search, the **Cards view and the read-only Availability Board** (with the day navigator and the "now"
line), and a management command `seed_rooms` that creates 6 sample school rooms in different buildings plus a few
approved reservations for today and tomorrow.
*Done when:* `/` shows rooms in the new glass design (palette, Inter, `msu_logo.png` in the sidebar); the search marks
an approved-overlap room as Occupied; the board shows the seeded reservations as blocks at the right times; the layout
works on a 360px wide screen; text on glass passes AA contrast; the page still looks fine with `backdrop-filter`
disabled; scrolling and hover animations are smooth.

**Phase B: Accounts.** Register (User + Profile), login, logout, redirects by role, navbar changes when logged in.
*Done when:* a new user can register, log in, log out; staff land on `/manage/`; Reserve on a room redirects to login and returns.

**Phase C: Reservations (requester).** Create, My Reservations, edit, cancel with all validation messages, and
click-a-free-slot on the Availability Board prefilling the reservation form.
*Done when:* overlapping, past, bad-time, and over-capacity requests are rejected with clear messages (also when
editing a pending request); users cannot touch other users' reservations.

**Phase D: Admin module.** Dashboard, reservations (tabs, approve, decline with remarks, conflict alert),
rooms CRUD with image upload, users, reports with print.
*Done when:* the full flow works: request -> admin approves -> room shows Occupied -> requester sees Approved.

**Phase E: Polish and handover.** Responsive check, error pages, empty states, pagination (10 per page) on long lists,
`README.md` (setup steps from `git clone` to `runserver`, how to create the admin, sample data),
a few automated tests for the overlap rule and the status flow (`python manage.py test`),
update `requirements.txt`.
*Done when:* tests pass and the README steps work on a clean machine.

## 12. Working rules for the agent

1. Work **one phase at a time**. At the end of each phase list: files created or changed, what each does,
   how to test it (exact commands and URLs), and any decision you made.
2. Make **small commits** with clear messages, one per logical step. Never commit secrets or `venv/`.
   Commit locally only; the students run `git push` themselves.
3. Do not add features that are not in this file. Suggest them at the end instead.
4. Do not change the data model, URL names, or package list without asking.
5. If a command fails, show the full error and your diagnosis. Do not hide failures or silence warnings.
6. Never run destructive commands without asking first: deleting or resetting migrations, `flush`,
   dropping or recreating the database, `git reset --hard`, `git push --force`, or deleting files outside
   the folders you created. The database contains the students' real test data.
7. Keep explanations in plain English; the students will present this code.
8. After finishing, give the students a short **demo script** (5 minutes) that shows every requirement
   FR-01 to FR-09 in order.

## 13. Requirement checklist (for the final demo)

| ID | Requirement | Where |
|---|---|---|
| FR-01 | Register, log in, log out; availability needs no login, reserving does | accounts, room list |
| FR-02 | Search rooms by date, time, building, capacity; Available or Occupied | room list (Cards and Availability Board) |
| FR-03 | Submit reservation (room, date, time, purpose, attendees) | reservation form |
| FR-04 | Conflict detection | `Reservation.clean()` + form errors |
| FR-05 | Approve or decline with remarks | dashboard reservations |
| FR-06 | View, edit, cancel own pending reservations | My Reservations |
| FR-07 | Manage rooms and users | dashboard rooms and users |
| FR-08 | Status updates shown to the user | My Reservations |
| FR-09 | History and printable reports | dashboard reports |
