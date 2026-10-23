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

## Outbound email queue

Every outbound email is written to a durable queue first and delivered later by
a background dispatcher. Nothing is sent inline with the request that triggered
it, so a large class roster can never spend the provider's whole daily quota in
one go, and a provider-side failure can never break the API call that created
an account.

The queue lives in the `email_outbox` table (created automatically at startup).
A dispatcher thread claims due messages with `FOR UPDATE SKIP LOCKED`, so
several backend replicas can run at the same time without sending a message
twice.

| Variable | What it controls |
| --- | --- |
| `EMAIL_TRANSPORT` | `smtp` (default) delivers over SMTP; `file` writes messages to disk instead |
| `EMAIL_DAILY_SEND_CAP` | Maximum deliveries per UTC day; defaults to `450` |
| `EMAIL_SEND_INTERVAL_SECONDS` | Minimum gap between two deliveries; defaults to `1.0` |
| `EMAIL_DISPATCH_INTERVAL_SECONDS` | How often the dispatcher looks for work; defaults to `5.0` |
| `EMAIL_SMTP_MAX_ATTEMPTS` | Attempts per message for transient errors; defaults to `3` |
| `EMAIL_SMTP_RETRY_BACKOFF_SECONDS` | Base backoff between attempts; defaults to `2.0` |
| `EMAIL_SMTP_CIRCUIT_BREAKER_SECONDS` | How long delivery pauses after a quota error; defaults to `300` |
| `EMAIL_QUOTA_BACKOFF_SECONDS` | How long a message waits after a quota error; defaults to `1800` |
| `EMAIL_QUEUE_MAX_ATTEMPTS` | How often the queue retries a failing message before giving up; defaults to `5` |

Behaviour:

- **Daily cap.** The dispatcher counts what it has already sent today and stops
  at `EMAIL_DAILY_SEND_CAP`. The rest stays queued and is delivered the next
  day. The count is stored in the database, so the cap is shared by every
  replica.
- **Steady rate.** Deliveries are spaced by `EMAIL_SEND_INTERVAL_SECONDS`, so a
  450-message backlog drains over roughly 7.5 minutes instead of arriving as
  one burst.
- **Quota errors.** When the provider answers with a sending-limit error
  (Gmail: `550 5.4.5 Daily user sending limit exceeded`), the message is put
  back with a delay, delivery is paused for the circuit-breaker window, and the
  log records a single warning instead of a stack trace per request. Accounts
  are still created; only the email is delayed.
- **Transient vs permanent errors.** 4xx SMTP replies and connection failures
  are retried with exponential backoff. Authentication failures and other 5xx
  replies are not retried.

### `signup_email_sent`

The API still reports `signup_email_sent` for backwards compatibility, but the
message is now *queued* rather than already delivered. The field is `true` when
the message was accepted into the outbox.

### Local development and demos

Set `EMAIL_TRANSPORT=file` to write every message to `EMAIL_OUTBOX_PATH`
(`backend/logs/email-outbox` by default) instead of contacting a provider. The
`.eml` files contain the real setup links, so the flow can be demonstrated
without consuming any sending quota or waiting on a real inbox.

### Suppressing notifications for a bulk import

A large CSV import can skip notifications entirely:

```text
POST /api/v1/courses/{course_id}/students/import?suppress_notifications=true
```

The students are still created and enrolled, and the import is still audited,
but no in-app notification and no password-setup email is produced. Use it for
rosters of hundreds of students; the affected students can request their
first-time setup email individually.

## Switching to a different email provider

Only `EMAIL_SMTP_*` and `EMAIL_FROM_ADDRESS` change. The queue, the daily cap
and the retry logic are provider independent.

| Provider | `EMAIL_SMTP_HOST` | `EMAIL_SMTP_PORT` | `EMAIL_SMTP_USERNAME` | `EMAIL_SMTP_PASSWORD` |
| --- | --- | --- | --- | --- |
| Gmail / Google Workspace | `smtp.gmail.com` | `587` | your address | app password |
| Microsoft 365 | `smtp.office365.com` | `587` | your address | app password |
| SendGrid | `smtp.sendgrid.net` | `587` | `apikey` | SG API key |
| Resend | `smtp.resend.com` | `587` | `resend` | `re:` API key |
| Mailgun | `smtp.mailgun.org` | `587` | `postmaster@<domain>` | SMTP password |
| Amazon SES | `email-smtp.<region>.amazonaws.com` | `587` | SMTP username | SMTP password |

`EMAIL_FROM_ADDRESS` must be a sender address the provider has verified. For
SendGrid, Resend, Mailgun and SES this is usually a domain you own rather than
a personal mailbox.

A transactional provider is worth the switch for a production deployment:
Gmail is capped at 500 messages per day per mailbox, and the cap applies to
every message the backend sends, including password resets and report
notifications.


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

### Fallback password

The emailed link is the primary way in, but it depends on the provider
delivering the message. An instructor or admin can set an **optional** password
when creating a student instead. The student can then log in with it **once**
and is immediately forced onto the change-first-password screen, exactly like
the emailed flow.

- The account is always created with `must_change_password = true`, so the
  fallback password works for a single login and no more.
- The password is never returned in any API response, and it is stored only as a
  PBKDF2 hash.
- A student created *without* a password gets a random placeholder that nobody
  knows, so the emailed link is the only way in. If it never arrives, an admin
  can still recover the account with `POST /api/v1/users/{user_id}/reset-password`.

The bulk CSV import always creates accounts without a usable password, because
a shared password in a roster file is not acceptable. For a large import, use
`?suppress_notifications=true` and hand out per-student passwords afterwards
with the admin reset endpoint.

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

Add `?suppress_notifications=true` to skip the in-app notifications and
password-setup emails for the imported students. The response reports this as
`"notifications_suppressed": true`. See
[Outbound email queue](#outbound-email-queue) for why this matters on large
imports.

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

Removals are notified too, so a student is never left guessing why access
disappeared:

| `event_type` | Title | Sent when |
| --- | --- | --- |
| `course_enrollment` | Added to a course | The student is enrolled in a course |
| `course_unenrollment` | Removed from a course | The student is unenrolled. Unenrolling also drops them from their project group in that course, and the message names the group |
| `course_deletion` | Course deleted | The whole course is deleted. Every enrolled student is told, and the message names their project group when they had one |
| `project_membership` | Added to a project | The student is added to a project group |
| `project_unmembership` | Removed from a project | The student is removed from a project group |
| `project_deletion` | Project deleted | The whole project group is deleted. Every member is told; the course itself is unaffected |
| `document_uploaded` | Student uploaded a document | A student uploads documents to a project |

The dashboard renders each event with its own label chip, and tints removals and
deletions in rose so they are visually distinct from additions.

Deactivating a student removes them from every course and project group, but
no notification is created for it: the account is disabled at that point, so
the student cannot sign in to read their feed.

