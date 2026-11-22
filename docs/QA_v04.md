# VietFrame Studio v0.4 — Login & owner authentication QA

## Completed in current development environment

- Python backend test suite: **51 / 51 PASS** (2026-11-22).
- `node --check static/app.js` and `node --check static/login.js`: PASS.
- Chromium static visual checks: 1440x900, 768x1024, 390x844, 360x760: PASS, no horizontal overflow, login form visible.
- HTTP client integration: first owner setup -> protected project API -> logout -> protected API returns 401: PASS.
- Existing FFmpeg render pipeline test (2s synthetic video, Vietnamese subtitles): PASS.

## Security capabilities implemented

- Single owner: first-run setup, then account creation locked.
- Remote initial setup requires `VIETFRAME_SETUP_TOKEN`; otherwise only loopback setup is allowed.
- PBKDF2-HMAC-SHA256 with random salt + 600,000 rounds; no default user/password.
- Random login session token is stored as SHA-256 hash in SQLite; HttpOnly, SameSite=Strict, 7-day session.
- All project/video/audio/AI APIs require a valid owner session. Mutation requests require a per-session CSRF header and same-origin validation.
- Rate limit: 8 failed logins per client IP in a 15-minute window.
- Logout deletes current server session; password change invalidates every session.

## Limits: not approved for public commercial rollout

- **One account only.** This is deliberate until project ownership scoping is implemented.
- Rate limiting is specific to login, not all AI jobs or uploads. No quotas or billing system.
- Public deployment still needs TLS, secure cookies, trusted reverse-proxy settings, backups, queue isolation, rate limits, SSRF audit, secure media storage, and a security review.
- Browser automation could not navigate to the localhost server due browser environment policy. Static Chromium layout inspection and HTTP integration tests were completed separately. Do **not** claim full browser E2E PASS.
- This release does not claim font match 1:1, watermark inpainting, or generative video QA success.
