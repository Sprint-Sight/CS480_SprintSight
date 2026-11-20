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

## Jira burndown and historical CSV imports

The Jira tab in Artifact Viewer shows the burndown for the selected ingestion
run. A live Jira sprint uses its native sprint dates and issue changelog. A CSV
import does not recreate that changelog, even when the imported issues have
`Done` as their current status. For a historical CSV demo, configure custom Jira
date fields for the imported dates in `backend/.env`:

| Environment variable | Jira field to configure |
| --- | --- |
| `JIRA_COMPLETED_DATE_FIELD` | Custom Date Picker field mapped from `Completed Date` |
| `JIRA_SPRINT_START_DATE_FIELD` | Custom Date Picker field mapped from `Sprint Start Date` |
| `JIRA_SPRINT_END_DATE_FIELD` | Custom Date Picker field mapped from `Sprint End Date` |

Set each value to its Jira field ID, such as `customfield_12345`, not its
display name. Restart the backend, sync the Jira sprint again, and process that
new run. These configured dates take precedence over Jira's import-time
resolution timestamp and sprint metadata. They let SprintSight reconstruct a
historical chart; they do not create actual Jira status history.

For the supplied CSV, map the columns as follows:

| CSV column | Jira field / import guidance |
| --- | --- |
| `Work Type` | Issue Type; ensure each value is a valid issue type in the Jira project |
| `Summary` | Summary |
| `Description` | Description |
| `Parent` | Parent relationship; the CSV values are numeric source IDs, not generated Jira issue keys. Use the importer's Issue ID/Parent ID linking if available; otherwise import parent rows first and connect children using their newly generated Jira keys |
| `Priority` | Priority; values must match priorities configured in the project |
| `Story Point Estimate` | The numeric story-points field used by the board. Set `JIRA_STORY_POINTS_FIELD` to that field's ID if it is not the default `customfield_10016` |
| `Assignee` | Assignee; values must resolve to Jira users who can be assigned issues |
| `Reporter` | Reporter; values must resolve to Jira users |
| `Sprint` | Assign each issue to a real sprint on the project's Scrum board. A text value alone does not create the sprint or its dates |
| `Status` | Current Jira status only. All sprint-assigned rows in this CSV are `Done`; this does not restore when they were completed |
| `Labels` | Labels |
| `Sprint Start Date` / `Sprint End Date` | Custom Jira Date Picker fields configured above; these are not native sprint dates |
| `Completed Date` | Custom Jira Date Picker field configured above; this is not a Jira status transition |
| `Issue Key` | Values such as `11` are source IDs, not Jira issue keys. Do not map them to Jira's Issue Key. Keep them in a dedicated source-ID field if needed |

Create the board sprints with the intended names and dates, then confirm the
issues are assigned to those sprints and have story points before syncing.
Keep the source IDs stable if using them to rebuild parent relationships.
Assignee and Reporter values must match Jira accounts; correct unmatched users
before relying on the resulting team-level data. Use the date format
`YYYY-MM-DD` for date columns.

The attached CSV has 63 sprint-assigned rows and 9 rows without a Sprint. Its
Sprint 3 group contains 9 issues and 26 points, matching the response shown in
the earlier chart output. However, that response's `2026-11-02` to
`2026-11-16` dates do not match the CSV's Sprint 3 dates (`2024-10-15` to
`2024-10-28`). Configure the date fields and resync/reprocess to use the CSV
dates. For a realistic live-sprint demo, import the issues as unfinished, then
start the Jira sprint and move issues to Done as work is completed; only Jira's
actual transitions produce native changelog history.

## AI Insights and MLflow

The AI engine records how every grade was produced in MLflow (see
[`ai-engine/README.md`](../ai-engine/README.md#mlflow-in-sprintsight)). The backend turns that
record into the **AI Insights** pages for instructors and admins: judge checks, flagged citations, a
trace timeline, prompt versions, and a comparison of the AI's scores with the instructor's. It also
copies instructor overrides back into MLflow as human feedback. Everything lives under
`/api/v1/insights` and `app/services/insightsService/`.

Four rules shape the design:

1. **Postgres is the index; MLflow is read by explicit trace ID only.** The backend never searches
   MLflow from user input. Each report stores its own `trace_id`, and that is the only key used.
2. **MLflow is optional at runtime.** If it is down, lists and scores still load from Postgres and the
   trace and judge panels show a notice. Writes to MLflow are queued and retried.
3. **Nothing sensitive leaves MLflow.** Prompts, model outputs and student code are stripped; only a
   small allow-list of numbers and timings is returned.
4. **Judge results never reveal themselves early.** One gate decides when an instructor may see them.

### How a report is linked to MLflow

```text
ai-engine response (trace_id)
  -> assessmentService.convert_ai_result_to_assessment_report   stores trace_id on the report
  -> assessment_reports.trace_id          the join key to the MLflow trace
  -> assessment_reports.ai_rubric_scores_original   the AI's own scores, written once
```

`ai_rubric_scores_original` is a snapshot taken when the report is created. The save query keeps the
existing value if the report is written again, so an instructor override can never change the
baseline that "adjustment" and the override statistics are measured from.

### Code map

| File | Responsibility |
| --- | --- |
| `app/services/insightsService/mlflow_gateway.py` | The only module that talks to MLflow. `RealMlflowGateway` reads a trace, writes and updates human feedback, lists prompt versions, and reports health. Calls time out after `MLFLOW_HTTP_REQUEST_TIMEOUT` seconds with no retries, and trace summaries are cached briefly (at most 256) |
| `app/services/insightsService/trace_summary.py` | Reduces an MLflow trace to the safe shape the UI shows: span names and timings, prompt versions, and an allow-list of judge assessments. Raw LLM calls (`AsyncCompletions`) are counted, never shown |
| `app/services/insightsService/judge.py` | Derives the judge status, builds the result tiles, and decides the "citation flagged" chip |
| `app/services/insightsService/citations.py` | The citations the judge did not fully accept. Prefers the structured verdicts the AI engine attaches as metadata (`sprintsight.citation_verdicts`, with a truncated flag) and falls back to parsing the rationale text for older traces |
| `app/services/insightsService/blind.py` | `authorize_score_view`, the single gate for AI scores and judge results; also the mode switch |
| `app/services/insightsService/overrides.py` | `record_override`, called after the Assessment Report editor saves |
| `app/services/insightsService/override_stats.py` | Override rate, mean adjustment and direction. Pure maths with no database access |
| `app/services/insightsService/label_sync.py` | The background worker that copies labels and overrides to MLflow and refreshes open judge statuses |
| `app/services/insightsService/service.py` | The use cases behind the routes (runs list, reveal, trace view, prompt views, health) |
| `app/services/insightsService/fake_gateway.py` | In-memory stand-in for MLflow, used by the tests |
| `app/repositories/insights.py` | Postgres and in-memory repositories and the idempotent schema |
| `app/dependencies/insights.py` | Access rules: the faculty-only guard and the per-report scope check |
| `app/api/v1/endpoints/insights.py` | The `/insights` routes |

### What is stored in Postgres

The tables are created at startup by `ensure_insights_schema` (every statement is idempotent) and
mirrored at the end of `init.sql`. They are all additive.

| Where | What |
| --- | --- |
| `assessment_reports.trace_id` | MLflow trace of the grading run |
| `assessment_reports.ai_rubric_scores_original` | The AI's original scores |
| `assessment_reports.judge_status`, `judge_checked_at`, `judge_summary` | Cached judge state and numbers, so lists never call MLflow |
| `report_overrides` | One row per report and dimension: the AI score, the instructor's score, whether it changed, and its MLflow sync state (`pending`, `synced`, `failed`, `no_trace`, `not_needed`) |
| `instructor_labels`, `report_view_log` | Used only by the blind-label mode: the labels, and when an instructor first saw AI results |

### The two modes

`INSIGHTS_MODE` selects how judge results unlock. It is read when the backend starts.

| Mode | Behaviour |
| --- | --- |
| `override_gate` (used in `docker-compose.yml`) | The AI score is always visible. Judge checks, flagged citations and the trace unlock for a report after an instructor saves an override on the Assessment Report page. Until then the Insights API returns `409`. Blind labelling is switched off |
| `blind_label` (the default in code) | The instructor scores all six dimensions before the AI results are revealed. The server enforces it and records whether labels were written before exposure |

Admins always see everything. The override data is recorded in both modes, so switching mode needs
no migration.

### Flows

**Judge status.** The AI engine judges a trace after grading, so a report starts as `pending`. The
sync worker re-checks open reports every `INSIGHTS_LABEL_SYNC_INTERVAL_SECONDS`, reads the trace, and
stores the status and a small summary on the report:

| Status | Meaning |
| --- | --- |
| `complete` | Both judge markers (`citation_hallucination_rate`, `narrative_contradiction_count`) are present |
| `failed` | A marker carries an error, or the engine skipped or gave up on the trace |
| `stale` | Still unfinished after `INSIGHTS_JUDGE_STALE_MINUTES` (default 120) |
| `pending` | Still running |
| `no_trace` | The report has no `trace_id`, or MLflow has no such trace |

A `failed`, `stale` or `no_trace` status can be wrong: the engine retries, a re-run replaces failed
assessments, and a judge or trace export can finish late. So reports that have a `trace_id` and are
less than 24 hours old are re-checked, at most once every 5 minutes.

**Overrides to MLflow.**

1. `PATCH /assessments/reports/{id}` saves the instructor's scores as before. A call to
   `record_override` then writes one `report_overrides` row per dimension. A failure there is logged
   and never fails the save.
2. Rows with a real change are marked `pending`. Rows with no change are `not_needed`, so a later
   reversion can still be detected.
3. The worker writes each pending row to the trace as a HUMAN assessment named
   `sprintsight.override.<dimension>` (score on a 0-10 scale), with metadata `blind=false`,
   `ai_score_original`, `changed` and the report ID. The instructor's user ID, never an email, is the
   source.
4. Before any first write the worker looks the assessment up by its feedback ID, so a retry after a
   lost response never creates a duplicate. A later edit updates the same assessment.
5. Errors keep the row `pending` and are retried; after 10 attempts it becomes `failed`. A report
   without a trace becomes `no_trace`.

**Reveal.** `GET /insights/reports/{id}/reveal` passes the gate, builds the AI-versus-instructor
table from the snapshot, then reads the trace for the judge tiles, the citations the judge did not
fully accept, and the prompt versions used.

**Prompt registry.** Admins can list the seven registered prompts with their `production`,
`challenger` and latest versions, and open any version with a diff against the previous one.
Instructors can open only the version their own report's trace recorded. Prompt names are checked
against a fixed list, so no free-text name ever reaches MLflow.

**Assessment progress.** The assessment job's progress events read the engine's `eval.progress` run
tag from MLflow (looked up by the job's correlation ID), so the UI can show how many steps are done.

### Routes

All routes sit under `/api/v1/insights`. A student gets `403` on every one, and a report that is
unknown or outside the caller's courses gets `404`, so report IDs cannot be probed.

| Route | Who | Purpose |
| --- | --- | --- |
| `GET /config` | Instructor, admin | Current mode (`override_gate` or `blind_label`) |
| `GET /my-courses` | Instructor, admin | Courses in scope, with counts |
| `GET /runs` | Instructor, admin | Graded runs, with filters, the "needs attention" flags and per-report sync status |
| `GET /reports/{id}/reveal` | Instructor, admin | AI-versus-instructor comparison, judge tiles, flagged citations, prompt versions. Gated |
| `GET /reports/{id}/trace` | Instructor, admin | Span timeline. Gated |
| `GET /reports/{id}/judge-status` | Instructor, admin | Status only, no values, so it is safe before unlocking |
| `GET /reports/{id}/prompts/{name}` | Instructor, admin | The prompt version this report used. Gated |
| `GET /reports/{id}/evidence` | Instructor, admin | Raw sprint evidence (commits, Jira, documents, peer data), never AI scores. Used by the blind-label flow |
| `PUT /reports/{id}/labels` | Instructor | Saves blind labels. Returns `409` in `override_gate` |
| `GET /override-stats` | Instructor, admin | How often and how far overrides changed AI scores. Not an accuracy measure |
| `GET /health` | Admin | MLflow reachability, client and server version match, telemetry state, items waiting to sync |
| `GET /prompt-registry`, `GET /prompt-registry/{name}/{version}` | Admin | Prompt versions, aliases and diffs |

### Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `MLFLOW_TRACKING_URI` | `http://host.docker.internal:5000` | MLflow server. Fixed in `docker-compose.yml` so a host-side `localhost` value cannot leak in |
| `MLFLOW_HTTP_REQUEST_TIMEOUT` | `5` | Seconds before an MLflow call gives up, so a stopped server cannot hang a page |
| `MLFLOW_HTTP_REQUEST_MAX_RETRIES` | `0` | No client retries; the sync worker does the retrying |
| `MLFLOW_DISABLE_TELEMETRY` | `true` | MLflow usage telemetry off |
| `INSIGHTS_ENABLED` | `true` | `false` removes the routes (kill switch); restart the backend |
| `INSIGHTS_MODE` | `blind_label` in code, `override_gate` in compose | See "The two modes" |
| `INSIGHTS_LABEL_SYNC_INTERVAL_SECONDS` | `30` in code, `10` in compose | How often the worker syncs and refreshes judge status |
| `INSIGHTS_JUDGE_STALE_MINUTES` | `120` | When an unfinished judge is shown as stale |

The MLflow server, the AI engine's `mlflow` and the backend's `mlflow-skinny` must be the same
version (3.16.1: `backend/pyproject.toml`, `ai-engine/requirements.txt`,
`ai-engine/mlflow-server/Dockerfile`). The admin health panel shows whether they match.

### Testing

The tests use `FakeMlflowGateway` and in-memory repositories, so they need no running MLflow:

```bash
cd backend
pytest tests/test_insights_*.py
```

They cover access rules for every route and mode (student 403, out of scope 404, admin 200), the
override gate, the sync worker (including a lost response and MLflow being down), judge-status
rules, citation parsing and the structured-metadata path, the override statistics, and that both
repository implementations provide the same methods.

To fill a local database with demo reports, labels and overrides:

```bash
docker exec sprintsight-backend python -m scripts.seed_insights_demo
```

### Turning it off

- Set `INSIGHTS_ENABLED=false` and restart to remove the routes and hide the Insights pages.
- Set `INSIGHTS_MODE=blind_label` and restart to switch back to blind labelling.
- The new columns and tables are additive and can stay. Human feedback already written to MLflow is
  named `sprintsight.override.*` or `sprintsight.instructor.*`, so it can be found and removed
  without touching the AI engine's own assessments.
