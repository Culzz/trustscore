# Security Policy

## Scope

TrustScore is a **demonstration**: it processes synthetic or public, non-personal
data and makes explicitly-labelled simulated decisions. If that scope is
respected, the realistic attack surface is the API service itself
(`api/`, the FastAPI app).

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

* Use GitHub's **"Report a vulnerability"** flow
  (*Security → Report a vulnerability* on the repository), or
* email an outline of the issue via the contact on
  [https://github.com/Culzz](https://github.com/Culzz).

Include the affected file/endpoint, the reproduction steps and your assessment
of impact. You will get a response within a few days; fixes land on `main` and
are acknowledged here once shipped.

## Built-in safeguards

* **Privacy gateway.** A pure-ASGI middleware strips direct identifiers (names,
  emails, phone numbers, addresses) from JSON request bodies before handlers run;
  only salted digests remain, for counting. The redaction count is echoed in
  `x-pii-redactions`.
* **Anonymised logging.** Prediction/drift logging stores bin indices and
  category codes, never raw applicant values.
* **No secrets in code or history.** All configuration is environment-based
  (documented in `.env.example`); `.env*` is git-ignored.
* **Rate limiting** (`RATE_LIMIT`, slowapi) on the scoring endpoints and a
  closed-by-default CORS allow-list (`CORS_ORIGINS`).
* **Simulation firewall.** Nothing in this repository makes or claims to make
  real credit decisions, holds funds, or transmits personal data anywhere.

## Deployment guidance

If you deploy your own instance: change `PII_SALT` from the default, set real
CORS origins for your domain, keep `MODEL_VERSION` pinned to a version that
exists in the committed registry, and point `ALERT_WEBHOOK_URL` only at
webhooks you control.
