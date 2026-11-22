"""Google OpenID Connect owner sign-in with server-side state, PKCE and ID-token verification.

Only the pre-authorized email may sign in, and a Google subject is bound permanently
on first success. Never stores Google access/refresh tokens. No paid API necessary.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit

import httpx
import jwt

from . import auth, config

AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_CERTS = 'https://www.googleapis.com/oauth2/v3/certs'
STATE_COOKIE = 'vf_google_flow'
STATE_TTL = 600


def settings():
    """Explicit env-only configuration; never expose the OAuth client secret to browser."""
    client_id = os.getenv('VIETFRAME_GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.getenv('VIETFRAME_GOOGLE_CLIENT_SECRET', '').strip()
    allowed = os.getenv('VIETFRAME_GOOGLE_ALLOWED_EMAIL', '').strip().casefold()
    origin = os.getenv('VIETFRAME_GOOGLE_ORIGIN', '').strip().rstrip('/')
    u = urlsplit(origin)
    secure_origin = u.scheme == 'https' and bool(u.hostname) and not (u.username or u.password or u.query or u.fragment or u.path)
    # Localhost only for development and integration tests.
    if u.scheme == 'http' and u.hostname in ('127.0.0.1','localhost') and not (u.query or u.fragment or u.path):
        secure_origin = True
    try:
        allowed = auth.normalize_email(allowed)
    except ValueError:
        allowed = ''
    return {'enabled': bool(client_id and client_secret and allowed and secure_origin),
            'client_id': client_id, 'client_secret': client_secret,
            'allowed_email': allowed, 'origin': origin if secure_origin else ''}


def redirect_uri(s):
    return s['origin'] + '/api/auth/google/callback'


def _connection():
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.execute('PRAGMA busy_timeout=30000')
    return con


def init():
    with _connection() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS google_oauth_states (
            state_hash TEXT PRIMARY KEY,
            verifier TEXT NOT NULL,
            nonce TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS google_oauth_states_expiry ON google_oauth_states(expires_at)')


def _digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def start():
    s = settings()
    if not s['enabled']:
        raise ValueError('Đăng nhập Google chưa được cấu hình trong Render.')
    state = secrets.token_urlsafe(40)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
    with _connection() as con:
        con.execute('DELETE FROM google_oauth_states WHERE expires_at < ?', (int(time.time()),))
        con.execute('''INSERT INTO google_oauth_states(state_hash,verifier,nonce,expires_at)
            VALUES(?,?,?,?)''', (_digest(state), verifier, nonce, int(time.time()) + STATE_TTL))
    url = AUTHORIZATION_URL + '?' + urlencode({
        'client_id': s['client_id'],
        'redirect_uri': redirect_uri(s),
        'response_type': 'code',
        'scope': 'openid email',
        'state': state,
        'nonce': nonce,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'access_type': 'online',
    })
    return url, state


def consume(state, cookie):
    if not (state and cookie and len(state) <= 128 and len(cookie) <= 128 and hmac.compare_digest(state, cookie)):
        raise PermissionError('Phiên đăng nhập Google không hợp lệ hoặc đã hết hạn.')
    with _connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT verifier,nonce,expires_at FROM google_oauth_states WHERE state_hash=?',
                          (_digest(state),)).fetchone()
        con.execute('DELETE FROM google_oauth_states WHERE state_hash=?', (_digest(state),))
    if not row or row[2] <= int(time.time()):
        raise PermissionError('Phiên Google đã hết hạn hoặc đã được sử dụng.')
    return row[0], row[1]


def _verify_id_token(id_token, client_id):
    # PyJWT validates Google's RSA signature, exp, aud and iss; no unverified claims
    # may reach the owner-binding code.
    jwks = jwt.PyJWKClient(GOOGLE_CERTS, timeout=12, lifespan=3600)
    public_key = jwks.get_signing_key_from_jwt(id_token).key
    return jwt.decode(id_token, public_key, algorithms=['RS256'], audience=client_id,
                      issuer=['https://accounts.google.com', 'accounts.google.com'],
                      options={'require': ['exp','iat','aud','iss','sub']}, leeway=30)


def exchange(code, verifier, nonce):
    s = settings()
    if not s['enabled']:
        raise PermissionError('Chưa cấu hình Google OAuth.')
    if not code or len(code) > 4096:
        raise PermissionError('Google không trả mã xác thực hợp lệ.')
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            res = client.post(TOKEN_URL, data={
                'grant_type': 'authorization_code', 'code': code,
                'client_id': s['client_id'], 'client_secret': s['client_secret'],
                'redirect_uri': redirect_uri(s), 'code_verifier': verifier,
            })
        res.raise_for_status()
        payload = res.json()
        claims = _verify_id_token(payload['id_token'], s['client_id'])
    except (httpx.HTTPError, KeyError, ValueError, jwt.PyJWTError) as exc:
        # Never emit secret, authorization code or id_token in errors.
        raise PermissionError('Google không xác minh được đăng nhập. Kiểm tra Client ID và Redirect URI.') from exc
    if not isinstance(claims, dict) or not hmac.compare_digest(str(claims.get('nonce','')), nonce):
        raise PermissionError('Mã xác nhận Google không khớp.')
    if claims.get('email_verified') is not True:
        raise PermissionError('Email Google chưa được xác minh.')
    try:
        email = auth.normalize_email(str(claims['email']))
    except (ValueError, KeyError) as exc:
        raise PermissionError('Google không cung cấp email hợp lệ.') from exc
    if not hmac.compare_digest(email, s['allowed_email']):
        raise PermissionError('Tài khoản Google này không phải chủ sở hữu VietFrame.')
    sub = str(claims.get('sub', ''))
    if not sub or len(sub) > 255:
        raise PermissionError('Mã tài khoản Google không hợp lệ.')
    return auth.google_owner(email, sub, allowed_email=s['allowed_email'])
