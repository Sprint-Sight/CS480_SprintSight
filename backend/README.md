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
| `EMAIL_API_BASE_URL` | Public backend base URL used in emailed API instructions |
| `EMAIL_ACTION_TOKEN_EXPIRE_MINUTES` | Password-action token lifetime; defaults to 30 |

The provider's **SMTP/API key goes in `EMAIL_SMTP_PASSWORD`** in
`backend/.env`. Do not put it in `EMAIL_FROM_ADDRESS`; that must be a verified
sender email address. The variables and placeholders are also listed in
[`backend/.env.example`](./.env.example). Never commit the actual `.env` file
or share its credentials.

## Password setup and reset API

Creating a managed account or resetting its temporary password sends a
first-time-password email when SMTP is configured. Users can request a fresh
setup email or a password-reset email:

- `POST /api/v1/auth/first-time-password/request` with `{"email":"user@example.com"}`
- `POST /api/v1/auth/password-reset/request` with `{"email":"user@example.com"}`

Both return a generic `202` response to avoid disclosing whether an account is
registered. The email contains a short-lived, single-use token. Complete the
requested action by POSTing `{"token":"<email token>","new_password":"..."}` to
the corresponding `/complete` endpoint. Password changes invalidate the token
and existing access tokens. The older authenticated `/auth/change-password`
route remains available for the current frontend; no frontend files were
changed. The unauthenticated `/users/change-password` route was removed
because it allowed password changes with only an email address.

## Assessment completion notifications

After the assessment report has been saved, each active instructor assigned to
its course receives a completion email with the project, sprint, report ID, and
team score. A mail-delivery failure is logged and recorded as a
`notification_failed` assessment-job event; it does not change the completed
report's status.
