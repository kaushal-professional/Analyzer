# Fyers Login Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 identified issues in `auth/fyers_login.py` — retry logic, IST timestamps, refresh token rotation, lazy credentials, narrower exceptions, SDK timeout, unused import.

**Architecture:** All changes are in a single file (`auth/fyers_login.py`). No new files. Public API (`get_fyers_token()`, `get_fyers_client()`) remains unchanged. Two new stdlib imports added (`time`, `zoneinfo`), one new stdlib import (`concurrent.futures`) for SDK timeout.

**Tech Stack:** Python 3.9+, requests, pyotp, fyers-apiv3, zoneinfo (stdlib)

---

### Task 1: Remove unused import and add new imports

**Files:**
- Modify: `auth/fyers_login.py:36-46`

- [ ] **Step 1: Remove `import base64` and add new imports**

Replace lines 36-46:

```python
import base64           # for base64 encoding (PIN in some endpoints)
import json             # for reading/writing the token cache file
import os               # for file paths and environment
import sys              # for modifying Python's module search path
import logging          # for structured log messages
import requests         # for making HTTP requests to Fyers API
import pyotp            # for generating TOTP codes (same as Google Authenticator)
from datetime import date, datetime  # for checking if cached token is from today
from hashlib import sha256           # for computing appIdHash (SHA256)
from urllib.parse import parse_qs, urlparse  # for extracting auth_code from redirect URL
from fyers_apiv3 import fyersModel   # official Fyers SDK for token exchange
```

With:

```python
import json             # for reading/writing the token cache file
import os               # for file paths and environment
import sys              # for modifying Python's module search path
import time             # for retry delay (time.sleep)
import logging          # for structured log messages
import requests         # for making HTTP requests to Fyers API
import pyotp            # for generating TOTP codes (same as Google Authenticator)
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime         # for timestamp-based cache expiry
from hashlib import sha256           # for computing appIdHash (SHA256)
from urllib.parse import parse_qs, urlparse  # for extracting auth_code from redirect URL
from zoneinfo import ZoneInfo        # for IST timezone (Asia/Kolkata)
from fyers_apiv3 import fyersModel   # official Fyers SDK for token exchange
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add auth/fyers_login.py
git commit -m "chore: remove unused base64 import, add time/zoneinfo/concurrent.futures imports"
```

---

### Task 2: Add `_post_with_retry()` helper

**Files:**
- Modify: `auth/fyers_login.py` — insert new function after `_app_id_hash()` (after line 107)

- [ ] **Step 1: Add the retry helper function**

Insert after the `_app_id_hash()` function (after line 107):

```python


# Maximum number of retry attempts for transient network failures
MAX_RETRIES = 5
# Seconds to wait between retry attempts
RETRY_DELAY = 2


def _post_with_retry(url: str, headers: dict, json_payload: dict,
                     timeout: int = 10) -> dict:
    """
    POST request with retry logic for transient network failures.

    Retries up to MAX_RETRIES times on ConnectionError and Timeout.
    Does NOT retry on API-level errors (4xx, wrong credentials, etc.)
    — those are permanent failures.

    Returns: parsed JSON response dict on success.
    Raises: requests.RequestException if all retries exhausted.
            ValueError if response is not valid JSON.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=json_payload, headers=headers,
                                 timeout=timeout)
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                logger.debug(f"Retry {attempt}/{MAX_RETRIES} for {url}: {e}")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for {url}: {e}")
    raise last_exc
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add auth/fyers_login.py
git commit -m "feat: add _post_with_retry helper with 5 attempts and 2s delay"
```

---

### Task 3: Replace `requests.post()` calls with `_post_with_retry()` and narrow exceptions

**Files:**
- Modify: `auth/fyers_login.py` — functions: `refresh_access_token`, `step1_send_login_otp`, `step2_verify_totp`, `step3_verify_pin`, `step4_get_auth_code`, `step5_validate_auth_code` (Method B)

- [ ] **Step 1: Rewrite `refresh_access_token()`**

Replace the entire `refresh_access_token` function body (lines 139-171) with:

```python
    try:
        payload = {
            "grant_type": "refresh_token",
            "appIdHash": _app_id_hash(),
            "refresh_token": refresh_token,
            "pin": str(FYERS_PIN),
        }

        data = _post_with_retry(
            "https://api-t1.fyers.in/api/v3/validate-refresh-token",
            headers=HEADERS, json_payload=payload
        )

        if data.get("s") == "ok" and data.get("access_token"):
            logger.info("Refresh token ✓")
            return {
                "access_token": data["access_token"],
                # Use new refresh_token if provided, otherwise keep the old one
                "refresh_token": data.get("refresh_token", refresh_token),
            }
    except requests.RequestException as e:
        logger.debug(f"Refresh network error: {e}")
    except (KeyError, ValueError) as e:
        logger.debug(f"Refresh parse error: {e}")

    return {}
```

Note: This also implements Fix 4 (refresh token rotation) — `data.get("refresh_token", refresh_token)` uses the new token if the API returns one.

- [ ] **Step 2: Rewrite `step1_send_login_otp()`**

Replace the function body (lines 201-223) with:

```python
    try:
        d = _post_with_retry(
            "https://api-t2.fyers.in/vagator/v2/send_login_otp",
            headers=HEADERS,
            json_payload={"fy_id": FYERS_USERNAME, "app_id": "2"}
        )

        if d.get("s") == "ok":
            logger.info("Step 1: send_login_otp ✓")
            return d["request_key"]
        else:
            logger.error(f"Step 1 FAILED: {d.get('message', d)}")
    except requests.RequestException as e:
        logger.error(f"Step 1 network error: {e}")
    except (KeyError, ValueError) as e:
        logger.error(f"Step 1 parse error: {e}")

    return ""
```

- [ ] **Step 3: Rewrite `step2_verify_totp()`**

Replace the function body (lines 250-278) with:

```python
    try:
        otp = pyotp.TOTP(FYERS_TOTP_SECRET).now()

        d = _post_with_retry(
            "https://api-t2.fyers.in/vagator/v2/verify_otp",
            headers=HEADERS,
            json_payload={"request_key": request_key, "otp": otp}
        )

        if d.get("s") == "ok":
            logger.info("Step 2: verify_totp ✓")
            return d["request_key"]
        else:
            logger.error(f"Step 2 FAILED: {d.get('message', d)}")
    except requests.RequestException as e:
        logger.error(f"Step 2 network error: {e}")
    except (KeyError, ValueError) as e:
        logger.error(f"Step 2 parse error: {e}")

    return ""
```

- [ ] **Step 4: Rewrite `step3_verify_pin()`**

Replace the function body (lines 307-330) with:

```python
    try:
        d = _post_with_retry(
            "https://api-t2.fyers.in/vagator/v2/verify_pin",
            headers=HEADERS,
            json_payload={
                "request_key": request_key,
                "identity_type": "pin",
                "identifier": str(FYERS_PIN),
            }
        )

        if d.get("s") == "ok":
            logger.info("Step 3: verify_pin ✓")
            return d["data"]["access_token"]
        else:
            logger.error(f"Step 3 FAILED: {d.get('message', d)}")
    except requests.RequestException as e:
        logger.error(f"Step 3 network error: {e}")
    except (KeyError, ValueError) as e:
        logger.error(f"Step 3 parse error: {e}")

    return ""
```

- [ ] **Step 5: Rewrite `step4_get_auth_code()`**

Replace the function body (lines 366-416) with:

```python
    try:
        app_id = FYERS_APP_ID.split("-")[0]
        h = {**HEADERS, "Authorization": f"Bearer {access_token}"}

        payload = {
            "fyers_id": FYERS_USERNAME,
            "app_id": app_id,
            "redirect_uri": FYERS_REDIRECT_URL,
            "appType": "100",
            "code_challenge": "",
            "state": "sample_state",
            "scope": "",
            "nonce": "",
            "response_type": "code",
            "create_cookie": True,
        }

        d = _post_with_retry(
            "https://api-t1.fyers.in/api/v3/token",
            headers=h, json_payload=payload
        )

        if d.get("s") == "ok":
            redirect_url = d.get("Url", "")
            parsed = urlparse(redirect_url)
            auth_code = parse_qs(parsed.query).get("auth_code", [""])[0]

            if auth_code:
                logger.info("Step 4: get_auth_code ✓")
                return auth_code

        logger.error(f"Step 4 FAILED: {d}")
    except requests.RequestException as e:
        logger.error(f"Step 4 network error: {e}")
    except (KeyError, ValueError) as e:
        logger.error(f"Step 4 parse error: {e}")

    return ""
```

- [ ] **Step 6: Rewrite `step5_validate_auth_code()` Method B only**

Replace the Method B try/except block (lines 472-502) with:

```python
    # ---- Method B: Direct API call (fallback) ----
    try:
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": _app_id_hash(),
            "code": auth_code,
        }

        d = _post_with_retry(
            "https://api-t1.fyers.in/api/v3/validate-authcode",
            headers=HEADERS, json_payload=payload
        )

        if d.get("s") == "ok":
            logger.info("Step 5: validate_auth_code ✓ (direct API)")
            return {
                "access_token": d.get("access_token", ""),
                "refresh_token": d.get("refresh_token", ""),
            }
        else:
            logger.error(f"Step 5 FAILED: {d}")
    except requests.RequestException as e:
        logger.error(f"Step 5 network error: {e}")
    except (KeyError, ValueError) as e:
        logger.error(f"Step 5 parse error: {e}")

    return {}
```

- [ ] **Step 7: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add auth/fyers_login.py
git commit -m "feat: use _post_with_retry in all API calls, narrow exception handling, handle refresh token rotation"
```

---

### Task 4: Add SDK timeout wrapper in Step 5 Method A

**Files:**
- Modify: `auth/fyers_login.py` — `step5_validate_auth_code()` Method A block

- [ ] **Step 1: Replace Method A try/except with threaded timeout**

Replace the Method A block (the first try/except in `step5_validate_auth_code`) with:

```python
    # ---- Method A: Use Fyers SDK (with 15s timeout) ----
    try:
        session = fyersModel.SessionModel(
            client_id=FYERS_APP_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URL,
            response_type="code",
            grant_type="authorization_code",
        )
        session.set_token(auth_code)

        # Wrap SDK call in a thread with timeout — generate_token() has no
        # built-in timeout and can hang indefinitely
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(session.generate_token)
            resp = future.result(timeout=15)

        if resp.get("s") == "ok" or resp.get("code") == 200:
            logger.info("Step 5: validate_auth_code ✓ (SDK)")
            return {
                "access_token": resp.get("access_token", ""),
                "refresh_token": resp.get("refresh_token", ""),
            }
    except FuturesTimeoutError:
        logger.warning("Step 5 SDK timed out after 15s, trying direct API...")
    except Exception as e:
        logger.debug(f"Step 5 SDK: {e}")
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add auth/fyers_login.py
git commit -m "feat: add 15s timeout to SDK generate_token() call via ThreadPoolExecutor"
```

---

### Task 5: IST timestamp-based cache expiry

**Files:**
- Modify: `auth/fyers_login.py` — `save_token()` and `get_fyers_token()`

- [ ] **Step 1: Add IST timezone constant after TOKEN_FILE**

Insert after line 73 (`TOKEN_FILE = ...`):

```python

# IST timezone for all timestamp operations
IST = ZoneInfo("Asia/Kolkata")

# Maximum token age in hours before re-login is required
# Fyers tokens last ~24h; 22h gives a 2-hour safety margin
MAX_TOKEN_AGE_HOURS = 22
```

- [ ] **Step 2: Update `save_token()` to use IST timestamps**

Replace the `data = {...}` block inside `save_token()` with:

```python
    now_ist = datetime.now(IST)
    data = {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "timestamp": now_ist.isoformat(),   # "2026-04-15T13:30:01.123456+05:30"
    }
```

Note: the `"date"` field is removed — we now use `timestamp` for age-based checks.

- [ ] **Step 3: Update `get_fyers_token()` Strategy 1 to use timestamp age check**

Replace the Strategy 1 block in `get_fyers_token()`:

```python
    # ---- Strategy 1: Reuse today's cached token ----
    # If the token was generated today, it's still valid (~24h lifetime)
    if cached.get("date") == date.today().isoformat() and cached.get("access_token"):
        logger.info("Using cached token (valid today)")
        return cached["access_token"]  # no API calls needed
```

With:

```python
    # ---- Strategy 1: Reuse cached token if still fresh ----
    # Token is valid if age < MAX_TOKEN_AGE_HOURS (22h, gives 2h safety margin on 24h lifetime)
    if cached.get("timestamp") and cached.get("access_token"):
        try:
            saved_time = datetime.fromisoformat(cached["timestamp"])
            now_ist = datetime.now(IST)
            age_hours = (now_ist - saved_time).total_seconds() / 3600
            if age_hours < MAX_TOKEN_AGE_HOURS:
                logger.info(f"Using cached token ({age_hours:.1f}h old)")
                return cached["access_token"]
            else:
                logger.info(f"Cached token expired ({age_hours:.1f}h old)")
        except (ValueError, TypeError):
            logger.debug("Could not parse cached timestamp, will re-login")
```

- [ ] **Step 4: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add auth/fyers_login.py
git commit -m "feat: IST timestamp-based cache expiry with 22h max age"
```

---

### Task 6: Lazy credential loading

**Files:**
- Modify: `auth/fyers_login.py` — module-level imports and credential access pattern

- [ ] **Step 1: Replace eager credential imports with lazy loading**

Replace lines 52-60:

```python
# Import credentials from config/settings.py which reads from .env file
from config.settings import (
    FYERS_APP_ID,       # e.g., "OBOYSW9YS8-100" — your API app ID
    FYERS_SECRET_KEY,   # secret key from myapi.fyers.in dashboard
    FYERS_REDIRECT_URL, # e.g., "https://v0-fyersanalysis.vercel.app" — must match dashboard
    FYERS_USERNAME,     # e.g., "FAI84781" — your Fyers client ID
    FYERS_PIN,          # e.g., "1234" — your 4-digit login PIN
    FYERS_TOTP_SECRET   # e.g., "JBSWY3DPEHPK3PXP" — secret from 2FA setup
)
```

With:

```python
# Credentials are loaded lazily via _get_credentials() to avoid reading
# secrets into memory at import time. The config module is imported here
# but values are only accessed when login is actually attempted.
import config.settings as _settings


def _get_credentials() -> dict:
    """
    Load credentials lazily from config.settings.

    Returns dict with all 6 credential values.
    Called only when login is actually needed, not at import time.
    """
    return {
        "app_id": _settings.FYERS_APP_ID,
        "secret_key": _settings.FYERS_SECRET_KEY,
        "redirect_url": _settings.FYERS_REDIRECT_URL,
        "username": _settings.FYERS_USERNAME,
        "pin": _settings.FYERS_PIN,
        "totp_secret": _settings.FYERS_TOTP_SECRET,
    }
```

- [ ] **Step 2: Update `_app_id_hash()` to use `_get_credentials()`**

Replace:

```python
    return sha256(f"{FYERS_APP_ID}:{FYERS_SECRET_KEY}".encode()).hexdigest()
```

With:

```python
    creds = _get_credentials()
    return sha256(f"{creds['app_id']}:{creds['secret_key']}".encode()).hexdigest()
```

- [ ] **Step 3: Update all step functions to use `_get_credentials()`**

In every function that references the old credential names, replace the old names with `creds = _get_credentials()` at the top and access via `creds[...]`:

- `refresh_access_token`: `FYERS_PIN` → `creds["pin"]`
- `step1_send_login_otp`: `FYERS_USERNAME` → `creds["username"]`
- `step2_verify_totp`: `FYERS_TOTP_SECRET` → `creds["totp_secret"]`
- `step3_verify_pin`: `FYERS_PIN` → `creds["pin"]`
- `step4_get_auth_code`: `FYERS_APP_ID` → `creds["app_id"]`, `FYERS_USERNAME` → `creds["username"]`, `FYERS_REDIRECT_URL` → `creds["redirect_url"]`
- `step5_validate_auth_code` Method A: `FYERS_APP_ID` → `creds["app_id"]`, `FYERS_SECRET_KEY` → `creds["secret_key"]`, `FYERS_REDIRECT_URL` → `creds["redirect_url"]`
- `full_totp_login`: Replace the manual creds check with `creds = _get_credentials()` and `missing = [k for k, v in creds.items() if not v]`
- `get_fyers_client`: `FYERS_APP_ID` → `_get_credentials()["app_id"]`

- [ ] **Step 4: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add auth/fyers_login.py
git commit -m "feat: lazy credential loading — secrets only read when login is attempted"
```

---

### Task 7: Update module docstring

**Files:**
- Modify: `auth/fyers_login.py:1-30`

- [ ] **Step 1: Update the module docstring to reflect changes**

Replace `date` reference in `LOGIN STRATEGY` section line 9:

```
  1. Check if today's token is cached in auth/.fyers_token → reuse it
```

With:

```
  1. Check if cached token is < 22h old (IST) in auth/.fyers_token → reuse it
```

And in `DEPENDENCIES` section line 29, no change needed (same deps).

- [ ] **Step 2: Commit**

```bash
git add auth/fyers_login.py
git commit -m "docs: update module docstring to reflect IST timestamp cache"
```

---

### Task 8: Final verification

- [ ] **Step 1: Full syntax check**

Run: `python -c "import ast; ast.parse(open('auth/fyers_login.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 2: Verify all 7 fixes are present**

Run a quick grep to confirm each fix:

```bash
# Fix 1: no base64 import
python -c "assert 'import base64' not in open('auth/fyers_login.py').read(); print('Fix 1 OK')"

# Fix 2: retry helper exists
python -c "assert '_post_with_retry' in open('auth/fyers_login.py').read(); print('Fix 2 OK')"

# Fix 3: IST timestamp
python -c "assert 'Asia/Kolkata' in open('auth/fyers_login.py').read(); print('Fix 3 OK')"

# Fix 4: refresh token rotation
python -c "assert 'data.get(\"refresh_token\", refresh_token)' in open('auth/fyers_login.py').read(); print('Fix 4 OK')"

# Fix 5: lazy credentials
python -c "assert '_get_credentials' in open('auth/fyers_login.py').read(); print('Fix 5 OK')"

# Fix 6: narrower exceptions
python -c "assert 'requests.RequestException' in open('auth/fyers_login.py').read(); print('Fix 6 OK')"

# Fix 7: ThreadPoolExecutor timeout
python -c "assert 'ThreadPoolExecutor' in open('auth/fyers_login.py').read(); print('Fix 7 OK')"
```

Expected: All 7 print `OK`.

- [ ] **Step 3: Final commit (if any remaining changes)**

```bash
git status
# If clean, nothing to commit. If any remaining changes:
git add auth/fyers_login.py
git commit -m "chore: final cleanup for fyers_login fixes"
```
