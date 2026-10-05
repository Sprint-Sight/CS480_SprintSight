# CS480_SprintSight
An automated continuous sprint assessment platform to streamline software engineering team evaluations.


# Navigate to your frontend directory
cd c:/Users/jchuj/sprintsight/CS480_SprintSight/frontend

# Install the runtime packages
npm install react react-dom lucide-react recharts

# Install the TypeScript type definitions as development dependencies
# Note: lucide-react has built-in types, so it doesn't need an @types package
npm install --save-dev @types/react @types/react-dom @types/recharts

## Audit retention and Postman checks

Audit events are stored in PostgreSQL for 168 days (24 weeks). The Compose
`audit-retention` worker runs the archive job immediately at startup and every
24 hours after that. It writes gzip NDJSON archives and JSON manifests to the
MinIO `audit-archive` bucket. Routine action and score-override archives both
expire after 365 days. Set `AUDIT_HOT_RETENTION_DAYS`,
`AUDIT_ACTION_ARCHIVE_RETENTION_DAYS`, `AUDIT_OVERRIDE_ARCHIVE_RETENTION_DAYS`,
`AUDIT_ARCHIVE_BATCH_SIZE`, or `MINIO_BUCKET_AUDIT_ARCHIVE` in `backend/.env` to
override these defaults.

### Migrate existing JSONL logs

Start PostgreSQL and MinIO, then from `backend/` run:

```powershell
docker compose up -d db minio
docker compose run --rm backend python -m app.services.auditLogService.legacy_import
```

The importer is safe to rerun. Records missing an ID receive a deterministic
SHA-256-based ID; existing IDs are preserved. It leaves `logs/audit.log`
untouched. Invalid lines are skipped and their line numbers are reported; the
source file is never rewritten. Preserve and review those lines before treating
the migration as complete. Verify imported counts and sample events in
PostgreSQL before retiring the old file.

### API and Postman tests

Start the app with `docker compose up -d` from `backend/`. The interactive API
and request-body schemas are at [http://localhost:8000/docs](http://localhost:8000/docs).
The audit APIs are:

- `GET http://localhost:8000/api/v1/audit/actions`
- `GET http://localhost:8000/api/v1/audit/overrides`

Both require a bearer token. Instructors see only their own events; admins see
all events; students receive `403`.

In Postman, create `base_url = http://localhost:8000/api/v1`. Log in with
`POST {{base_url}}/auth/login` and body `{"email":"...","password":"..."}`.
Save the response `access_token` as `instructor_token` or `admin_token`, then
set Authorization to Bearer Token `{{instructor_token}}` or
`{{admin_token}}`. Use `/docs` for the exact request bodies and prerequisites.
Run each mutation successfully, then call `/audit/actions` and check the event
name, actor ID/role, target ID, and relevant non-sensitive details.

Instructor/course event routes include:

- `POST`, `PATCH`, `DELETE /courses` and `/courses/{course_id}`: `create_course`, `update_course`, `delete_course`.
- `POST`, `DELETE /courses/{course_id}/students/{user_id}`: `enroll_course_student`, `unenroll_course_student`.
- `POST /courses/{course_id}/instructors/{user_id}` and `POST /courses/{course_id}/students`: `assign_course_instructor`, `create_course_student` (or `enroll_course_student` when enrolling an existing account).
- `POST /courses/{course_id}/projects`, `PATCH /projects/{project_id}`, `DELETE /projects/{project_id}`: `create_project`, `update_project`, `delete_project`.
- `POST`, `DELETE /projects/{project_id}/members/{user_id}`: `add_project_member`, `remove_project_member`.
- `POST /assessments/assess`, `PUT /assessments/rubric-weights`, `PATCH /assessments/reports/{report_id}`: `request_assessment`, `update_rubric_weights`, `update_assessment_report`.
- `POST /repo-ingestion/sync` and `POST /jira-ingestion/raw/{project_id}`: `sync_repository_ingestion`, `sync_raw_jira_data`.
- `POST /projects/{project_id}/documents` and `POST /manual-text`: `upload_project_documents`, `update_manual_sprint_text`.
- `POST /auth/change-password` and `POST /auth/logout`: `change_own_password`, `logout`.

Admin/user event routes include `POST /users` (`create_user`),
`PATCH /users/{user_id}` (`update_user`),
`POST /users/{user_id}/reset-password` (`reset_password`),
`DELETE /users/{user_id}` (`deactivate_user`), and
`POST /users/{user_id}/activate` (`activate_user`). Check that password-reset
events contain no password or token values.

For score overrides, submit a valid `POST /assessments/override` and check
`GET /audit/overrides`; overrides are a separate audit record type, not an
`/audit/actions` event. Finally, restart the backend and repeat both GETs to
confirm events persist in PostgreSQL.

### Verify retention

Do not wait 24 weeks or change timestamps through a public API. Automated tests
cover cutoff behavior, archive expiry, deterministic month batches, malformed
JSONL, failed uploads, failed archive verification, and restoring an archived
month. Run them from `backend/` with `python -m pytest tests/test_audit_retention.py -q`.

For an end-to-end deletion check, use a development database only. Insert one
synthetic old action row and capture the returned ID and month:

```powershell
docker compose exec -T db psql -U postgres -d sprintsight -c "INSERT INTO action_audit_events (audit_id, actor_id, actor_role, action, target_type, target_id, details, created_at) VALUES ('retention-smoke-' || gen_random_uuid()::text, 'retention-smoke-actor', 'instructor', 'retention_smoke', 'test', 'retention-smoke-target', jsonb_build_object('synthetic', TRUE), NOW() - INTERVAL '169 days') RETURNING audit_id, to_char(created_at, 'YYYY-MM');"
```

Run the worker once; the Postgres advisory lock makes this safe if the daily
worker is running at the same time:

```powershell
docker compose run --rm backend python -m app.services.auditLogService.retention
```

Confirm the returned ID now has zero rows in PostgreSQL, while its archive
manifest reports `record_count: 1`. Check `docker compose logs audit-retention`
for archived/deleted counts and failures. To read back the archive, use the
month returned by the INSERT (for example `2026-04`):

```powershell
docker compose run --rm backend python -m app.services.auditLogService.archive_reader --category actions --month 2026-04 --output /app/restored-smoke.jsonl
```

The reader verifies object metadata, compressed and uncompressed size, both
SHA-256 checksums, and row count before writing restored NDJSON. Confirm the
synthetic ID is present in `restored-smoke.jsonl`.

After a successful daily run, this query should show `over_retention = 0` for
both categories:

```sql
SELECT 'actions' AS category, COUNT(*) AS total,
	   COUNT(*) FILTER (WHERE created_at < NOW() - INTERVAL '168 days') AS over_retention
FROM action_audit_events
UNION ALL
SELECT 'overrides', COUNT(*),
	   COUNT(*) FILTER (WHERE timestamp < NOW() - INTERVAL '168 days')
FROM override_audit_events;
```

Inspect gzip objects and `.manifest.json` files in MinIO's `audit-archive`
bucket (console: `http://localhost:9001`). Each daily batch has a deterministic
key containing its month, event-time range, and content checksum; distinct
partial batches in the same month cannot overwrite one another. The worker is
the **only archive-expiry mechanism**; no MinIO lifecycle expiry is configured.
Objects include SHA-256, count, and size metadata. PostgreSQL deletes make
space reusable but may not immediately reduce database file size; rely on
autovacuum rather than routine `VACUUM FULL`.

The DB trigger rejects UPDATEs and ordinary DELETEs; the retention repository
sets a transaction-local flag and deletes only the verified primary-key list.
This is a guard against accidental application mutations, not a security
boundary against the current Compose `postgres` superuser; strict separation
requires separate runtime and retention database roles.