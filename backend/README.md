# Backend email configuration

Email notifications use SMTP, so the same settings work with providers such as
Google Workspace, Microsoft 365, SendGrid, and Resend. Configure these values
in `backend/.env` (the file is local and gitignored):

| Variable | Value from your email provider |
| --- | --- |
| `EMAIL_SMTP_HOST` | SMTP server hostname (for example, `smtp.sendgrid.net`) |
| `EMAIL_SMTP_PORT` | Usually `587` for STARTTLS or `465` for SSL |
| `EMAIL_SMTP_USERNAME` | SMTP username (for SendGrid this is commonly `apikey`) |
| `EMAIL_SMTP_PASSWORD` | SMTP password or provider-issued SMTP/API key |
| `EMAIL_FROM_ADDRESS` | Sender address on a domain verified with the provider |
| `EMAIL_FROM_NAME` | Friendly sender name; defaults to `SprintSight` |
| `EMAIL_SMTP_USE_TLS` | `true` for STARTTLS, normally used with port `587` |
| `EMAIL_SMTP_USE_SSL` | `true` for implicit SSL, normally used with port `465` |
| `EMAIL_FRONTEND_BASE_URL` | Public frontend base URL used for clickable password links |
| `EMAIL_FIRST_TIME_TOKEN_EXPIRE_MINUTES` | First-time password link lifetime; defaults to 1440 (24 hours) |
| `EMAIL_PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | Password-reset link lifetime; defaults to 30 |

The provider's **SMTP/API key goes in `EMAIL_SMTP_PASSWORD`** in
`backend/.env`. Do not put it in `EMAIL_FROM_ADDRESS`; that must be a verified
sender email address. The variables and placeholders are also listed in
[`backend/.env.example`](./.env.example). Never commit the actual `.env` file
or share its credentials.

For local Docker Compose testing, `EMAIL_FRONTEND_BASE_URL=http://localhost:3000`
works when the recipient opens the message on the same computer. For deployed
use, set it to the public HTTPS frontend URL so recipients can open the link.
Replace any old `EMAIL_API_BASE_URL` setting with `EMAIL_FRONTEND_BASE_URL`.
When frontend routes change, rebuild the Compose frontend so the running image
includes the new route: from `backend/`, run
`docker compose up -d --build frontend`.

## Password setup and reset API

Creating a managed account or resetting its temporary password sends a
first-time-password email when SMTP is configured. Users can request a fresh
setup email or a password-reset email:

Instructors can also create a student from a course roster without supplying a
password. The account is created with a random, undisclosed temporary password,
and sent a first-time setup link. The student is then enrolled separately from
the roster. A student can be enrolled in multiple courses, but only once per
course code. To apply this rule to an existing database, run
`docker compose exec -T db psql -U postgres -d sprintsight < migrations/20261020_student_course_code_unique.sql`
from `backend/`; the migration stops without changing enrollment data if
duplicate course-code enrollments already exist.

- `POST /api/v1/auth/first-time-password/request` with `{"email":"user@example.com"}`
- `POST /api/v1/auth/password-reset/request` with `{"email":"user@example.com"}`

Both return a generic `202` response to avoid disclosing whether an account is
registered. The email contains a clickable, single-use link to the frontend
password form. First-time setup links expire after 24 hours by default, while
reset links expire after 30 minutes; set the respective variables above to
change either lifetime. Password changes invalidate the token and existing
access tokens. The authenticated `/auth/change-password` route remains
available for temporary-password login; the unauthenticated
`/users/change-password` route was removed because it allowed password changes
with only an email address.

## Bulk course student import

Assigned instructors can import a course roster with:

```text
POST /api/v1/courses/{course_id}/students/import
```

Send a `multipart/form-data` request with a `file` field containing UTF-8 CSV
data with exactly these headers:

```csv
student_name,student_id,student_email
Student One,123456,student.one@example.edu
```

The import validates the complete file before enrolling anyone. Existing
student accounts are matched by numeric `student_id` or email; new accounts
are created with a generated temporary password and marked for first-time
password setup. Re-importing an already enrolled student is idempotent.
Student emails and supplied student numbers must be unique. Existing legacy
accounts without a student number are left unchanged; bulk CSV imports always
require a student number for each imported row.
Invalid rows, conflicting identity fields, disabled accounts, and students
already enrolled in another section of the same course offering reject the
import. The CSV is limited to 10 MB and 5,000 rows.

## Assessment completion notifications

After the assessment report has been saved, each active instructor assigned to
its course receives a completion email with the project, sprint, report ID, and
team score. Each active student included in the report also receives an email
with their own score. When an instructor changes an individual score or
manually updates a report, the affected student(s) receive an update email.
A mail-delivery failure is logged and recorded as a
`notification_failed` assessment-job event; it does not change the completed
report's status.

## Local in-app notifications

The backend stores in-app notifications in PostgreSQL and serves them from the
local API at `http://localhost:8000/api/v1/notifications`. The dashboard bell
refreshes the signed-in user's feed every 30 seconds. Students are notified
when enrolled in a course/class or added to a project; assigned instructors
are notified when a student uploads one or more project documents. Feed items
are private to their recipient and can be marked read with
`PATCH /api/v1/notifications/{notification_id}/read`.
