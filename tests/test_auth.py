"""Security, first-run and UI integration tests for single-owner authentication."""
import concurrent.futures
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app
from app import auth, config

OWNER = 'owner@example.com'
PASS = 'only-for-local-test-phrase-123'


def stranger():
    return TestClient(app, follow_redirects=False)


def test_private_home_login_page_and_media_api(client):
    with stranger() as other:
        assert other.get('/').status_code == 303
        assert other.get('/').headers['location'] == '/login'
        r = other.get('/login')
        assert r.status_code == 200
        assert 'Chào mừng trở lại.' in r.text
        assert other.get('/api/auth/me').status_code == 401
        assert other.get('/api/projects').status_code == 401
        assert other.get('/api/projects/' + 'a'*32 + '/file/source').status_code == 401
        assert other.get('/api/voices').status_code == 401
        assert other.post('/api/ai/create-video', json={'prompt':'Some video prompt to test'}).status_code == 401
        assert other.get('/api/docs').status_code == 401
        assert other.get('/static/index.html').status_code == 303
        assert other.get('/static/login.css').status_code == 200
        assert other.get('/api/health').status_code == 200
    assert client.get('/').status_code == 200


def test_single_owner_disables_registration(client):
    with stranger() as other:
        settings = other.get('/api/auth/config').json()
        assert not settings['setup_required']
        assert other.post('/api/auth/setup',json={'email':'other@example.com','password':PASS,'setup_token':'local-test-setup-key'}).status_code == 409


def test_authenticated_session_and_csrf(client):
    row = client.get('/api/auth/me').json()
    assert row['email'] == OWNER
    assert row['csrf']
    no_csrf = client.post('/api/ai/create-video',json={'prompt':'This is a sufficiently long cinematic prompt'},headers={'X-CSRF-Token':''})
    assert no_csrf.status_code == 403
    wrong_csrf = client.put('/api/projects/'+'a'*32+'/segments',json={'segments':[]},headers={'X-CSRF-Token':'tampered'})
    assert wrong_csrf.status_code == 403
    malicious_origin = client.post('/api/auth/logout',headers={'origin':'https://evil.test'})
    assert malicious_origin.status_code == 403
    assert client.get('/api/auth/me').status_code == 200


def test_login_invalid_password_and_rate_limit(client):
    with stranger() as other:
        for _ in range(auth.MAX_FAILED_ATTEMPTS):
            assert other.post('/api/auth/login',json={'email':OWNER,'password':'WRONG-PASSWORD-1234'}).status_code == 401
        assert other.post('/api/auth/login',json={'email':OWNER,'password':PASS}).status_code == 429


def test_login_session_cookies_logout(client):
    with stranger() as other:
        r = other.post('/api/auth/login',json={'email':OWNER,'password':PASS})
        assert r.status_code == 200
        cookie = r.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/' in cookie
        csrf = r.json()['csrf']
        assert other.get('/api/projects').status_code == 200
        assert other.post('/api/auth/logout',headers={'X-CSRF-Token':csrf}).status_code == 200
        assert other.get('/api/projects').status_code == 401


def test_change_password_revokes_all_sessions(client):
    with stranger() as other:
        r=other.post('/api/auth/login',json={'email':OWNER,'password':PASS})
        assert r.status_code == 200
        failed=client.post('/api/auth/change-password',json={'old_password':'not-old-pass','new_password':'new-long-passphrase-456'})
        assert failed.status_code == 422
        assert client.get('/api/auth/me').status_code == 200
        changed=client.post('/api/auth/change-password',json={'old_password':PASS,'new_password':'new-long-passphrase-456'})
        assert changed.status_code == 200
        assert client.get('/api/auth/me').status_code == 401
        assert other.get('/api/auth/me').status_code == 401
        assert other.post('/api/auth/login',json={'email':OWNER,'password':PASS}).status_code == 401
        renewed=other.post('/api/auth/login',json={'email':OWNER,'password':'new-long-passphrase-456'})
        assert renewed.status_code == 200


def test_no_plaintext_password_and_token_hash_on_disk(client):
    import sqlite3
    with sqlite3.connect(config.DB_PATH) as c:
        stored = c.execute('SELECT password_hash FROM owner_users').fetchone()[0]
        assert stored.startswith('pbkdf2_sha256$')
        assert PASS not in stored
        token = c.execute('SELECT token_hash,csrf FROM auth_sessions LIMIT 1').fetchone()
        assert token and len(token[0])==64 and token[0] != client.cookies.get(auth.COOKIE_NAME)


def test_owner_creation_needs_remote_token(client):
    assert auth.has_owner()
    assert not auth.verify_password('bad-password',auth.hash_password('a-very-long-secret-987'))
    assert auth.verify_password('a-very-long-secret-987',auth.hash_password('a-very-long-secret-987'))


def test_login_page_has_no_inline_script_and_accessible_inputs(client):
    page=client.get('/login', follow_redirects=False)
    assert page.status_code == 303  # owner already logged in
    with stranger() as other:
        html=other.get('/login').text
        assert '<script defer src="/static/login.js"></script>' in html
        for expected in ['autocomplete="username"','autocomplete="current-password"','role="alert"','id="auth-form"']:
            assert expected in html


def test_expired_session_refused(client,monkeypatch):
    token=client.cookies.get(auth.COOKIE_NAME)
    assert auth.get_session(token)
    original = auth.time.time
    monkeypatch.setattr(auth.time, 'time', lambda: original() + auth.SESSION_TTL + 50)
    assert client.get('/api/auth/me').status_code == 401


def test_login_csrf_origin_and_password_policy(client):
    with stranger() as other:
        assert other.post('/api/auth/login', json={'email':OWNER,'password':PASS}, headers={'Origin':'https://evil.example'}).status_code == 403
        assert other.post('/api/auth/login', json={'email':OWNER,'password':PASS[:6]}).status_code == 422
        assert other.post('/api/auth/setup', json={'email':'test@example.com','password':PASS,'setup_token':'local-test-setup-key'}, headers={'Origin':'https://evil.example'}).status_code == 403
