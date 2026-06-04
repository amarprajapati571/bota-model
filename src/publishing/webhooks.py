from __future__ import annotations

import hashlib
import hmac
import json


def sign_webhook_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={signature}"
