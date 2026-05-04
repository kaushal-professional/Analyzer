# Fyers Login Fixes — Design Spec

**Date:** 2026-04-15
**File:** `auth/fyers_login.py`
**Scope:** 7 targeted fixes. Same file, same public API (`get_fyers_token()`, `get_fyers_client()`).

---

## Fix 1: Remove unused `import base64`

Line 36 imports `base64` but it is never used. Delete it.

## Fix 2: Retry logic for transient failures

- Add a `_post_with_retry(url, json, headers, timeout)` helper.
- **5 attempts**, 2-second delay between retries.
- Only retry on network-level errors (`requests.ConnectionError`, `requests.Timeout`).
- Do NOT retry on API-level failures (wrong PIN, expired TOTP, HTTP 4xx) — those are permanent.
- All 6 HTTP calls in the file (Steps 1-5 + refresh) use this helper instead of `requests.post()` directly.

## Fix 3: Timestamp-based cache expiry with IST

- Replace the current date-only check (`cached["date"] == today`) with a timestamp age check.
- Use `Asia/Kolkata` (IST) for all timestamp comparisons via `zoneinfo.ZoneInfo`.
- Token is valid if age < 22 hours (2-hour safety margin on 24h lifetime).
- Save timestamps in ISO format with IST timezone info.
- Import `zoneinfo.ZoneInfo` (stdlib, Python 3.9+).

## Fix 4: Handle refresh token rotation

- In `refresh_access_token()`, check if the API response contains a new `refresh_token`.
- If present, return the new one instead of reusing the old one.
- This prevents failures when Fyers rotates the refresh token server-side.

## Fix 5: Lazy credential loading

- Currently all 6 credentials are imported at module top level — any `import auth.fyers_login` loads secrets into memory.
- Move credential reads into a `_get_credentials()` helper that is called lazily by `full_totp_login()` and `refresh_access_token()`.
- The `from config.settings import ...` stays at module level (just names), but actual values are accessed only when needed.

## Fix 6: Narrower exception handling

- Replace bare `except Exception` with specific catches:
  - `requests.RequestException` for HTTP/network failures.
  - `(KeyError, ValueError)` for malformed API responses.
- Keep a final `except Exception` only in the top-level `get_fyers_token()` as a last-resort safety net with a warning-level log.

## Fix 7: Timeout for SDK `generate_token()` call

- Step 5 Method A uses `session.generate_token()` which has no timeout.
- Wrap it in `concurrent.futures.ThreadPoolExecutor` with a 15-second timeout.
- On timeout, fall through to Method B (direct API call) which already has `timeout=10`.

---

## Non-goals

- No file restructuring or new modules.
- No test infrastructure (no consumers exist yet).
- No changes to `config/settings.py`.
- No changes to the public API surface.
