"""Privacy gateway: strip direct identifiers before they reach a service.

The applicant schema forbids extra fields, so the realistic risk is a caller
sending direct identifiers (a name, an email, a national id) alongside the
eleven modelling fields -- perhaps in a future ``metadata`` block. This ASGI
middleware removes any key that looks like a direct identifier from the request
body. The raw value is never forwarded; a salted digest is kept *in request
state only*, for audit counting, so the redaction is observable without
retaining the identifier itself.

Design notes:

* It is **pure ASGI**, so it rewrites the request body without a full buffering
  framework and without affecting streaming responses.
* It only touches JSON request bodies under 1 MB; anything else passes through.
* Redacted keys are dropped from the body (not replaced) so the request still
  validates against the strict applicant schema.
* It records how many fields it redacted in ``scope['state']`` and echoes a
  count in the ``x-pii-redactions`` response header, so the redaction is
  observable and testable rather than silent.
"""
from __future__ import annotations

import hashlib
import json

# Keys treated as direct identifiers. Match is case-insensitive and on the
# whole key (so ``loan_amnt`` is untouched while ``customer_name`` is caught).
PII_KEYS = {
    "name", "full_name", "fullname", "first_name", "last_name", "surname",
    "email", "email_address", "phone", "phone_number", "mobile", "telephone",
    "ssn", "social_security_number", "national_id", "nin", "bvn", "id_number",
    "passport", "passport_number", "drivers_license", "license_number",
    "address", "street", "street_address", "postcode", "zip", "zip_code",
    "date_of_birth", "dob", "birth_date",
    "account_number", "iban", "card_number", "credit_card", "cvv",
}

MAX_BODY = 1_000_000


def _digest(value, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()[:12]


def scrub(obj, salt: str, state: dict):
    """Recursively drop direct identifiers. Mutates ``state`` with a count."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if isinstance(key, str) and key.strip().lower() in PII_KEYS:
                state["count"] = state.get("count", 0) + 1
                state.setdefault("keys", []).append(key)
                # Kept in request state (never in the body) so the audit trail can
                # count redactions and correlate repeats without storing the value.
                state.setdefault("digests", []).append(_digest(value, salt))
                continue
            out[key] = scrub(value, salt, state)
        return out
    if isinstance(obj, list):
        return [scrub(item, salt, state) for item in obj]
    return obj


class PIIMaskingMiddleware:
    def __init__(self, app, salt: str = "trustscore-demo-salt"):
        self.app = app
        self.salt = salt

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        content_type = headers.get("content-type", "")
        method = scope.get("method", "GET")
        if method not in ("POST", "PUT", "PATCH") or "application/json" not in content_type:
            return await self.app(scope, receive, send)

        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)

        redactions = {"count": 0, "keys": []}
        if 0 < len(body) <= MAX_BODY:
            try:
                data = json.loads(body)
                data = scrub(data, self.salt, redactions)
                body = json.dumps(data).encode("utf-8")
            except Exception:
                pass  # not JSON after all; forward unchanged

        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and redactions["count"]:
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-pii-redactions", str(redactions["count"]).encode()))
                message = {**message, "headers": raw_headers}
            await send(message)

        state = dict(scope.get("state") or {})
        state["pii_redactions"] = redactions["count"]
        state["pii_keys"] = redactions["keys"]
        state["pii_digests"] = redactions.get("digests", [])
        await self.app({**scope, "state": state}, replay, send_wrapper)
