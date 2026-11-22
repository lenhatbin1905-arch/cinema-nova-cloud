"""Single-owner local-first authentication; no third-party API or paid service.

A new deployment requires either loopback access or a secret VIETFRAME_SETUP_TOKEN
for its first owner creation. Additional public sign-ups are intentionally disabled:
media projects are currently scoped to one owner only.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime, timezone

from . import config

COOKIE_NAME = 'vf_session'
SESSION_TTL = 180 * 24 * 3600  # User stays signed in on this browser for rolling 180 days
PASSWORD_ITERATIONS = 600_000
MAX_FAILED_ATTEMPTS = 8
FAILURE_WINDOW = 15 * 60


def _connection():
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init():
    with _connection() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS owner_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        cols = {r[1] for r in c.execute('PRAGMA table_info(owner_users)')}
        if 'google_sub' not in cols:
            c.execute('ALTER TABLE owner_users ADD COLUMN google_sub TEXT')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS owner_users_google_sub ON owner_users(google_sub)')
        c.execute('''CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES owner_users(id) ON DELETE CASCADE,
            csrf TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL)''')
        c.execute('''CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at)''')
        c.execute('''CREATE TABLE IF NOT EXISTS auth_failures (
            client_key TEXT NOT NULL, attempt_at INTEGER NOT NULL)''')
        c.execute('''CREATE INDEX IF NOT EXISTS auth_failures_key_at ON auth_failures(client_key,attempt_at)''')


def has_owner():
    with _connection() as c:
        return bool(c.execute('SELECT 1 FROM owner_users LIMIT 1').fetchone())


def normalize_email(email: str):
    e = email.strip().casefold()
    if not (5 <= len(e) <= 254) or e.count('@') != 1:
        raise ValueError('Địa chỉ email chưa hợp lệ.')
    name, host = e.split('@', 1)
    if not name or not host or '.' not in host or any(ch.isspace() for ch in e):
        raise ValueError('Địa chỉ email chưa hợp lệ.')
    return e


def validate_password(password: str):
    if not (12 <= len(password) <= 128):
        raise ValueError('Mật khẩu phải từ 12 đến 128 ký tự.')
    if len(password.encode('utf-8')) > 512:
        raise ValueError('Mật khẩu quá dài.')


def hash_password(password: str):
    validate_password(password)
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return f'pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${derived.hex()}'


def verify_password(password: str, stored: str):
    try:
        algo, rounds, salt, wanted = stored.split('$')
        if algo != 'pbkdf2_sha256' or not (100_000 <= int(rounds) <= 1_000_000):
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(wanted))
    except (ValueError, UnicodeError, TypeError):
        return False


_DUMMY_HASH = hash_password('not-a-real-password-1234')


def create_first_owner(email: str, password: str):
    address = normalize_email(email)
    digest = hash_password(password)
    with _connection() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM owner_users LIMIT 1').fetchone():
            raise ValueError('Tài khoản chủ sở hữu đã được tạo.')
        cursor = c.execute('INSERT INTO owner_users(email,password_hash,created_at) VALUES(?,?,?)',
                           (address, digest, datetime.now(timezone.utc).isoformat()))
        return {'id': cursor.lastrowid, 'email': address}


def google_owner(email: str, sub: str, *, allowed_email: str):
    """Single-owner Google binding, atomic under concurrent callbacks.

    A different Google subject can NEVER claim an already bound account,
    even if it presents the same email string.
    """
    address = normalize_email(email)
    if not hmac.compare_digest(address, normalize_email(allowed_email)) or not sub or len(sub) > 255:
        raise PermissionError('Tài khoản Google không được phép đăng nhập.')
    with _connection() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT id,email,google_sub FROM owner_users LIMIT 1').fetchone()
        if row is None:
            # Disable guessing/using a password for OAuth-first owners. An admin can
            # choose a local password later using reset-owner-password offline.
            password = hash_password(secrets.token_urlsafe(48))
            cursor = c.execute('INSERT INTO owner_users(email,password_hash,created_at,google_sub) VALUES(?,?,?,?)',
                               (address, password, datetime.now(timezone.utc).isoformat(), sub))
            return {'id': cursor.lastrowid, 'email': address}
        if not hmac.compare_digest(row['email'], address):
            raise PermissionError('Email Google khác email chủ sở hữu đang lưu.')
        if row['google_sub'] is None:
            c.execute('UPDATE owner_users SET google_sub=? WHERE id=? AND google_sub IS NULL', (sub, row['id']))
        elif not hmac.compare_digest(row['google_sub'], sub):
            raise PermissionError('Tài khoản Google không khớp với tài khoản đã liên kết.')
        return {'id': row['id'], 'email': row['email']}


def _limiter_key(client_ip: str):
    return hashlib.sha256(client_ip.encode('utf-8', errors='replace')).hexdigest()


def is_login_limited(client_ip: str):
    cutoff = int(time.time()) - FAILURE_WINDOW
    key = _limiter_key(client_ip)
    with _connection() as c:
        c.execute('DELETE FROM auth_failures WHERE attempt_at < ?', (cutoff,))
        count = c.execute('SELECT COUNT(*) FROM auth_failures WHERE client_key=?', (key,)).fetchone()[0]
        return count >= MAX_FAILED_ATTEMPTS


def record_failure(client_ip: str):
    with _connection() as c:
        c.execute('INSERT INTO auth_failures(client_key,attempt_at) VALUES(?,?)',
                  (_limiter_key(client_ip), int(time.time())))


def validate_login(email: str, password: str, client_ip: str):
    if is_login_limited(client_ip):
        raise PermissionError('Quá nhiều lần đăng nhập sai. Hãy thử lại sau 15 phút.')
    try:
        address = normalize_email(email)
    except ValueError:
        address = ''
    with _connection() as c:
        row = c.execute('SELECT * FROM owner_users WHERE email=?', (address,)).fetchone()
    valid = verify_password(password, row['password_hash'] if row else _DUMMY_HASH)
    if not (row and valid):
        record_failure(client_ip)
        return None
    with _connection() as c:
        c.execute('DELETE FROM auth_failures WHERE client_key=?', (_limiter_key(client_ip),))
    return {'id': row['id'], 'email': row['email']}


def new_session(user_id: int):
    session = secrets.token_urlsafe(40)
    csrf = secrets.token_urlsafe(32)
    now = int(time.time())
    with _connection() as c:
        c.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (now,))
        c.execute('INSERT INTO auth_sessions(token_hash,user_id,csrf,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (_token_hash(session), user_id, csrf, now + SESSION_TTL, now))
    return session, csrf


def _token_hash(token: str):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def get_session(token: str | None):
    if not token or len(token) > 256:
        return None
    with _connection() as c:
        row = c.execute('''SELECT s.token_hash,s.csrf,s.expires_at,u.id,u.email
            FROM auth_sessions s JOIN owner_users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?''', (_token_hash(token), int(time.time()))).fetchone()
    return dict(row) if row else None


def revoke_session(token: str):
    with _connection() as c:
        c.execute('DELETE FROM auth_sessions WHERE token_hash=?', (_token_hash(token),))


def change_password(user_id: int, old_password: str, new_password: str):
    validate_password(new_password)
    with _connection() as c:
        row = c.execute('SELECT password_hash FROM owner_users WHERE id=?', (user_id,)).fetchone()
    if row is None or not verify_password(old_password, row['password_hash']):
        return False
    new_hash = hash_password(new_password)
    with _connection() as c:
        c.execute('UPDATE owner_users SET password_hash=? WHERE id=?', (new_hash, user_id))
        c.execute('DELETE FROM auth_sessions WHERE user_id=?', (user_id,))
    return True


def reset_owner_password(new_password: str):
    """Administrator-only offline action; invalidates all sessions."""
    digest = hash_password(new_password)
    with _connection() as c:
        row = c.execute('SELECT id FROM owner_users LIMIT 1').fetchone()
        if row is None:
            raise ValueError('Chưa có chủ sở hữu để khôi phục mật khẩu.')
        c.execute('UPDATE owner_users SET password_hash=? WHERE id=?', (digest, row['id']))
        c.execute('DELETE FROM auth_sessions WHERE user_id=?', (row['id'],))


def _cli():
    import getpass
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action not in {'create-owner', 'reset-owner-password'}:
        print('Usage: python -m app.auth {create-owner|reset-owner-password}')
        return 2
    init()
    if action == 'create-owner':
        if has_owner():
            print('An owner account already exists; registration is locked.')
            return 1
        email = input('Owner email: ').strip()
    else:
        if not has_owner():
            print('No owner account exists.')
            return 1
    password = getpass.getpass('New password (12+ chars): ')
    confirmation = getpass.getpass('Confirm new password: ')
    if password != confirmation:
        print('Passwords do not match.')
        return 1
    try:
        if action == 'create-owner':
            create_first_owner(email, password)
        else:
            reset_owner_password(password)
    except ValueError as exc:
        print(str(exc))
        return 1
    print('Owner credentials saved. You can now sign in at /login.')
    return 0


# Hosted sessions are persisted in Neon, never in Render Free temporary SQLite.
from . import credential_store as _credential_store
if _credential_store.persistent():
    from . import auth_persistent as _remote
    init = _remote.init
    has_owner = _remote.has_owner
    create_first_owner = _remote.create_first_owner
    google_owner = _remote.google_owner
    is_login_limited = _remote.is_login_limited
    record_failure = _remote.record_failure
    validate_login = _remote.validate_login
    new_session = _remote.new_session
    get_session = _remote.get_session
    revoke_session = _remote.revoke_session
    change_password = _remote.change_password
    reset_owner_password = _remote.reset_owner_password


if __name__ == '__main__':
    raise SystemExit(_cli())
