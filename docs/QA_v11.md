# VietFrame v0.11 — Progress + ElevenLabs restricted-key QA

2026-11-22. Local test environment: Python 3.13, FastAPI TestClient, pytest, node --check. Source branch deploy/vietframe-fullstack-v08.

## Implemented

- Visible progress panel directly above video preview; server status, reported milestone percentage, step labels, and complete/error states.
- Gemini milestones after discrete, confirmed actions: initialize (11%), upload session (20%), uploaded (46%), Gemini File ACTIVE (67%), response requested (74%), received (91%), validated (97%), persisted (100%). No fabricated time countdown.
- Disabled Gemini subtitle analysis explains missing source; failed YouTube link can be recovered via upload of user-owned MP4 to same project (v0.10 feature).
- ElevenLabs restricted key can be linked only if /v2/voices succeeds, even if /v1/user is denied. Status explicitly says `limited` and User Read is needed to verify Free quota before creating paid-resource TTS. Unverified/potentially paid requests stay blocked.

## Tests

- `pytest -q --disable-warnings --maxfail=1`: 101 passed. Includes real ffmpeg integration tests and synthetic/mocked Gemini and ElevenLabs integration tests; NOT quality tests of a real provider account.
- `node --check static/app.js`: PASS.
- Python bytecode compile check of modified backend modules: PASS.
- Newly added tests: scoped ElevenLabs key accepted only after actual voices verification, rejected key cannot be persisted, Gemini progress callback phase order, UI progress semantics, error handling.

## Known constraints

- Render Free ephemeral data storage; deploy/restart can clear projects and encrypted provider keys. No production-grade persistent datastore.
- YouTube Shorts downloader can be denied by YouTube from Render IP despite modern yt-dlp + JS runtime. Users can recover project with an authorized local video file.
- Frontend percentage is milestone progress, not elapsed-time percent or a prediction; an external API call may remain at one milestone for an extended time. No fake ETA.
- Real Gemini subtitles or ElevenLabs TTS cannot be verified without valid, authorized user API keys and source video; never claim live end-to-end success based on mocks.
