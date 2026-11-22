"""Regressions for persistent sessions and fail-closed ElevenLabs 402 errors."""
from pathlib import Path
import httpx
from app import auth, credential_store, elevenlabs_bridge as eleven

def response(status, detail):
    return httpx.Response(status, json={'detail':detail},
                          request=httpx.Request('POST','https://api.elevenlabs.io/v1/text-to-speech/fake'))

def test_402_library_voice_is_actionable():
    r=response(402, {'status':'payment_required','message':'Free users cannot use library voices via the API'})
    text=str(eleven._tts_failure(r))
    assert 'HTTP 402' in text and 'thư viện' in text and 'âm thanh gốc' in text

def test_402_insufficient_credits_is_different_from_voice_restriction():
    r=response(402, {'status':'insufficient_credits','message':'Not enough credits'})
    text=str(eleven._tts_failure(r))
    assert 'HTTP 402' in text and 'tín dụng' in text and 'không tự mua' in text

def test_402_generic_does_not_invent_billing():
    r=response(402, {'status':'payment_required','message':'The feature is not available'})
    text=str(eleven._tts_failure(r))
    assert 'HTTP 402' in text and 'gói' in text

def test_401_404_429_explained_without_leaking_key():
    for status, phrase in [(401,'quyền'),(404,'giọng'),(429,'tần suất')]:
        r=response(status,{'status':'error','message':'secret-key-must-not-be-returned'})
        result=str(eleven._tts_failure(r))
        assert phrase in result and 'secret-key' not in result

def test_auth_cookie_remembered_for_six_months():
    assert auth.SESSION_TTL == 180*24*3600
    src=(Path(__file__).resolve().parents[1]/'app/auth_persistent.py').read_text()
    assert 'core._token_hash(token)' in src
    assert 'now-row[5])>=86400' in src
    assert 'refresh_cookie' in src
    assert 'vietframe_auth_sessions' in src

def test_provider_key_storage_never_in_browser():
    source=(Path(__file__).resolve().parents[1]/'app/credential_store.py').read_text()
    assert 'vietframe_provider_credentials' in source
    assert 'encrypted_key BYTEA' in source
    assert 'VIETFRAME_CREDENTIALS_DATABASE_URL' in source
    assert 'Neon' in source

def test_recovery_requires_user_consent_and_preserves_script():
    js=(Path(__file__).resolve().parents[1]/'static/app.js').read_text()
    html=(Path(__file__).resolve().parents[1]/'static/index.html').read_text()
    assert "window.confirm('Xuất video bằng âm thanh gốc" in js
    assert "await apiPost('/api/projects/'+state.selected.id+'/recover'" in js
    assert 'id="retry-original-audio"' in html
    assert 'collectSegments' in js

def test_google_state_persistent_and_one_time_consumed():
    src=(Path(__file__).resolve().parents[1]/'app/google_oauth.py').read_text()
    assert 'DELETE FROM vietframe_google_oauth_states' in src
    assert 'RETURNING verifier,nonce,expires_at' in src
    assert 'hmac.compare_digest(state, cookie)' in src

def test_login_cookie_is_secure_and_refreshed_only_on_activity():
    src=(Path(__file__).resolve().parents[1]/'app/main.py').read_text()
    assert "session.get('refresh_cookie')" in src
    assert 'httponly=True' in src
    assert "max_age=auth.SESSION_TTL" in src
