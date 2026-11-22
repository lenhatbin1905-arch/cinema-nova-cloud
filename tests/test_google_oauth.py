"""Google OIDC flow: allowlist, state cookie, nonce, PKCE and account binding."""
from urllib.parse import urlparse, parse_qs
import os
import secrets
import time

import pytest
from fastapi.testclient import TestClient
from app import auth, config, google_oauth as goo
from app.main import app


def google_config(monkeypatch, *, email='owner@example.com'):
    monkeypatch.setenv('VIETFRAME_GOOGLE_CLIENT_ID','example-client.apps.googleusercontent.com')
    monkeypatch.setenv('VIETFRAME_GOOGLE_CLIENT_SECRET','test-secret-not-production')
    monkeypatch.setenv('VIETFRAME_GOOGLE_ALLOWED_EMAIL',email)
    monkeypatch.setenv('VIETFRAME_GOOGLE_ORIGIN','https://vietframe-studio-app.onrender.com')


def visitor():
    return TestClient(app, follow_redirects=False)


def test_google_disabled_by_default_and_no_secret_leak(client, monkeypatch):
    monkeypatch.delenv('VIETFRAME_GOOGLE_CLIENT_ID', raising=False)
    monkeypatch.delenv('VIETFRAME_GOOGLE_CLIENT_SECRET', raising=False)
    with visitor() as other:
        settings = other.get('/api/auth/config').json()
        assert settings['google_login_available'] is False
        assert 'secret' not in str(settings).lower()
        page = other.get('/login').text
        assert 'id="google-login"' in page
        assert 'id="google-setup-guide"' in page
        resp = other.get('/api/auth/google/start')
        assert resp.status_code == 303
        assert resp.headers['location'] == '/login?google_error=not_configured'
        assert 'set-cookie' not in resp.headers


def test_google_configuration_needs_secure_origin_and_owner_allowlist(client, monkeypatch):
    google_config(monkeypatch)
    with visitor() as other:
        result=other.get('/api/auth/config').json()
        assert result['google_login_available'] is True
        assert 'VIETFRAME_GOOGLE_CLIENT_SECRET' not in str(result)
    monkeypatch.setenv('VIETFRAME_GOOGLE_ORIGIN','http://evil.example')
    assert not goo.settings()['enabled']
    monkeypatch.setenv('VIETFRAME_GOOGLE_ORIGIN','https://user:pass@fake.example')
    assert not goo.settings()['enabled']
    monkeypatch.setenv('VIETFRAME_GOOGLE_ORIGIN','https://vietframe-studio-app.onrender.com')
    monkeypatch.delenv('VIETFRAME_GOOGLE_ALLOWED_EMAIL')
    assert not goo.settings()['enabled']


def test_google_start_uses_pkce_state_nonce_browser_cookie(client, monkeypatch):
    google_config(monkeypatch)
    with visitor() as browser:
        response = browser.get('/api/auth/google/start')
        assert response.status_code == 303
        url = urlparse(response.headers['location'])
        assert url.scheme == 'https' and url.netloc == 'accounts.google.com'
        query = parse_qs(url.query)
        assert query['response_type'] == ['code']
        assert query['scope'] == ['openid email']
        assert query['code_challenge_method'] == ['S256']
        assert query['redirect_uri'] == ['https://vietframe-studio-app.onrender.com/api/auth/google/callback']
        assert 'client_secret' not in response.headers['location']
        state=query['state'][0]
        assert browser.cookies.get(goo.STATE_COOKIE) == state
        assert 'httponly' in response.headers['set-cookie'].lower()
        assert 'samesite=lax' in response.headers['set-cookie'].lower()
        verifier, nonce = goo.consume(state,state)
        assert len(verifier)>40 and nonce == query['nonce'][0]
        with pytest.raises(PermissionError):
            goo.consume(state,state)


def test_google_callback_creates_session_for_same_owner(client, monkeypatch):
    google_config(monkeypatch)
    calls=[]
    def fake_exchange(code, verifier, nonce):
        calls.append((code,verifier,nonce))
        return auth.google_owner('owner@example.com','10983945019283',allowed_email='owner@example.com')
    monkeypatch.setattr(goo,'exchange',fake_exchange)
    with visitor() as browser:
        start = browser.get('/api/auth/google/start')
        state = parse_qs(urlparse(start.headers['location']).query)['state'][0]
        result = browser.get('/api/auth/google/callback', params={'code':'from-google-code','state':state})
        assert result.status_code == 303 and result.headers['location']=='/'
        assert browser.get('/api/auth/me').status_code == 200
        assert browser.get('/api/auth/me').json()['email'] == 'owner@example.com'
        assert len(calls)==1 and calls[0][0]=='from-google-code'
        assert 'vf_session=' in result.headers.get('set-cookie','')
        assert 'samesite=lax' in result.headers.get('set-cookie','').lower()
        assert browser.cookies.get(goo.STATE_COOKIE) is None
        # A callback token cannot be replayed after consuming it.
        second = browser.get('/api/auth/google/callback',params={'code':'from-google-code','state':state})
        assert second.headers['location'].startswith('/login?google_error=')
        assert len(calls) == 1


def test_google_callback_rejects_cross_browser_state_and_error(client, monkeypatch):
    google_config(monkeypatch)
    monkeypatch.setattr(goo, 'exchange', lambda *args: pytest.fail('Should not exchange'))
    with visitor() as a, visitor() as b:
        start=a.get('/api/auth/google/start')
        state=parse_qs(urlparse(start.headers['location']).query)['state'][0]
        swapped=b.get('/api/auth/google/callback',params={'code':'x','state':state})
        assert swapped.status_code==303 and 'google_error=' in swapped.headers['location']
        assert b.get('/api/auth/me').status_code==401
        denied=a.get('/api/auth/google/callback',params={'error':'access_denied','state':state})
        assert denied.headers['location'] == '/login?google_error=cancelled'


def test_google_owner_initial_creation_and_subject_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'new.sqlite3')
    auth.init()
    google_config(monkeypatch, email='owner@example.com')
    first = auth.google_owner('owner@example.com','GOOGLE-UNIQUE-SUB-123',allowed_email='owner@example.com')
    assert first['email'] == 'owner@example.com'
    again = auth.google_owner('owner@example.com','GOOGLE-UNIQUE-SUB-123',allowed_email='owner@example.com')
    assert again['id']==first['id']
    with pytest.raises(PermissionError):
        auth.google_owner('owner@example.com','OTHER-SUB-456',allowed_email='owner@example.com')
    with pytest.raises(PermissionError):
        auth.google_owner('stranger@gmail.com','GOOGLE-UNIQUE-SUB-123',allowed_email='owner@example.com')
    assert auth.validate_login('owner@example.com','invented-password-abcdefg','127.0.0.1') is None


def test_google_existing_owner_email_mismatch_never_hijacks(client, monkeypatch):
    google_config(monkeypatch, email='stranger@gmail.com')
    with pytest.raises(PermissionError):
        auth.google_owner('stranger@gmail.com','ATTACKER-SUB',allowed_email='stranger@gmail.com')
    assert auth.has_owner()


def test_google_signed_token_audience_issuer_signature(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=private.public_key()
    class MockJWK:
        def __init__(self,*a,**kw):pass
        def get_signing_key_from_jwt(self,token):
            return type('S',(),{'key':public})()
    monkeypatch.setattr(goo.jwt,'PyJWKClient',MockJWK)
    now=int(time.time())
    claims={'sub':'sub-123','email':'owner@example.com','email_verified':True,'nonce':'abc',
            'aud':'example-client.apps.googleusercontent.com','iss':'https://accounts.google.com',
            'iat':now,'exp':now+300}
    def sign(extra=None):
        return jwt.encode({**claims,**(extra or {})},private,algorithm='RS256')
    assert goo._verify_id_token(sign(),claims['aud'])['nonce']=='abc'
    with pytest.raises(jwt.PyJWTError):
        goo._verify_id_token(sign({'aud':'attacker.apps.googleusercontent.com'}),claims['aud'])
    with pytest.raises(jwt.PyJWTError):
        goo._verify_id_token(sign({'iss':'https://wrong.issuer.example'}),claims['aud'])
    with pytest.raises(jwt.PyJWTError):
        goo._verify_id_token(sign({'exp':now-1000}),claims['aud'])
    other_private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(jwt.PyJWTError):
        goo._verify_id_token(jwt.encode(claims,other_private,algorithm='RS256'),claims['aud'])


def test_google_exchange_rejects_wrong_nonce_or_unverified_email(client,monkeypatch):
    google_config(monkeypatch)
    class FakeResponse:
        def raise_for_status(self):pass
        def json(self):return {'id_token':'signed-id-token-from-google'}
    class FakeHttp:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,data):
            assert url.startswith('https://oauth2.googleapis.com/')
            assert data['code_verifier'] == 'verifier'
            assert data['redirect_uri'].endswith('/api/auth/google/callback')
            return FakeResponse()
    monkeypatch.setattr(goo.httpx,'Client',FakeHttp)
    claims={'nonce':'mismatch','email':'owner@example.com','email_verified':True,'sub':'123456789'}
    monkeypatch.setattr(goo,'_verify_id_token',lambda *args:claims)
    with pytest.raises(PermissionError, match='Mã xác nhận'):
        goo.exchange('google-code','verifier','EXPECTED')
    claims['nonce']='EXPECTED'
    claims['email_verified']=False
    with pytest.raises(PermissionError, match='chưa được'):
        goo.exchange('google-code','verifier','EXPECTED')
    claims['email_verified']=True
    claims['email']='stranger@gmail.com'
    with pytest.raises(PermissionError, match='không phải chủ sở hữu'):
        goo.exchange('google-code','verifier','EXPECTED')
