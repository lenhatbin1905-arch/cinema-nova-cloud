"""Persistent single-owner accounts and 180-day rolling sessions in Neon Postgres.

Used only when VIETFRAME_CREDENTIALS_DATABASE_URL is set. Authentication
tokens remain random, HttpOnly and stored in Postgres only as SHA-256 hashes.
"""
import hashlib
import hmac
import secrets
import time
from . import auth as core
from . import credential_store as store

def _pg():
    return store._pg()

def init():
    with _pg() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS vietframe_owner_users (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id=1),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            google_sub TEXT UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS vietframe_auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id SMALLINT NOT NULL REFERENCES vietframe_owner_users(id) ON DELETE CASCADE,
            csrf TEXT NOT NULL, expires_at BIGINT NOT NULL,
            created_at BIGINT NOT NULL, last_seen_at BIGINT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS vietframe_auth_sessions_expiry ON vietframe_auth_sessions(expires_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS vietframe_auth_failures (
            client_key TEXT NOT NULL, attempt_at BIGINT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS vietframe_auth_failures_key_at ON vietframe_auth_failures(client_key,attempt_at)")

def has_owner():
    with _pg() as db:
        return db.execute('SELECT 1 FROM vietframe_owner_users LIMIT 1').fetchone() is not None

def create_first_owner(email,password):
    address=core.normalize_email(email)
    digest=core.hash_password(password)
    with _pg() as db:
        row=db.execute("""INSERT INTO vietframe_owner_users(id,email,password_hash)
          VALUES(1,%s,%s) ON CONFLICT DO NOTHING RETURNING id,email""",(address,digest)).fetchone()
        if row is None:
            raise ValueError('Tài khoản chủ sở hữu đã tồn tại.')
        return {'id':row[0],'email':row[1]}

def google_owner(email,sub,*,allowed_email):
    address=core.normalize_email(email)
    allowed=core.normalize_email(allowed_email)
    if not hmac.compare_digest(address,allowed) or not sub or len(sub)>255:
        raise PermissionError('Tài khoản Google không được phép đăng nhập.')
    with _pg() as db:
        row=db.execute('SELECT id,email,google_sub FROM vietframe_owner_users WHERE id=1 FOR UPDATE').fetchone()
        if row is None:
            digest=core.hash_password(secrets.token_urlsafe(48))
            row=db.execute("""INSERT INTO vietframe_owner_users(id,email,password_hash,google_sub)
              VALUES(1,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id,email,google_sub""",
              (address,digest,sub)).fetchone()
            if row is None:
                row=db.execute('SELECT id,email,google_sub FROM vietframe_owner_users WHERE id=1 FOR UPDATE').fetchone()
        if row is None or not hmac.compare_digest(str(row[1]),address):
            raise PermissionError('Email Google khác email chủ sở hữu.')
        if row[2] is None:
            db.execute('UPDATE vietframe_owner_users SET google_sub=%s WHERE id=%s AND google_sub IS NULL',(sub,row[0]))
        elif not hmac.compare_digest(str(row[2]),str(sub)):
            raise PermissionError('Tài khoản Google không khớp chủ sở hữu đã liên kết.')
        return {'id':row[0],'email':row[1]}

def _limiter_key(client_ip):
    return hashlib.sha256(client_ip.encode('utf-8',errors='replace')).hexdigest()

def is_login_limited(client_ip):
    cutoff=int(time.time())-core.FAILURE_WINDOW
    with _pg() as db:
        db.execute('DELETE FROM vietframe_auth_failures WHERE attempt_at < %s',(cutoff,))
        n=db.execute('SELECT COUNT(*) FROM vietframe_auth_failures WHERE client_key=%s',
                     (_limiter_key(client_ip),)).fetchone()[0]
        return n>=core.MAX_FAILED_ATTEMPTS

def record_failure(client_ip):
    with _pg() as db:
        db.execute('INSERT INTO vietframe_auth_failures(client_key,attempt_at) VALUES(%s,%s)',
                   (_limiter_key(client_ip),int(time.time())))

def validate_login(email,password,client_ip):
    if is_login_limited(client_ip):
        raise PermissionError('Quá nhiều lần đăng nhập sai. Hãy thử lại sau 15 phút.')
    try:
        address=core.normalize_email(email)
    except ValueError:
        address=''
    with _pg() as db:
        row=db.execute('SELECT id,email,password_hash FROM vietframe_owner_users WHERE email=%s',(address,)).fetchone()
    ok=core.verify_password(password,row[2] if row else core._DUMMY_HASH)
    if not (row and ok):
        record_failure(client_ip)
        return None
    with _pg() as db:
        db.execute('DELETE FROM vietframe_auth_failures WHERE client_key=%s',(_limiter_key(client_ip),))
    return {'id':row[0],'email':row[1]}

def new_session(user_id):
    token=secrets.token_urlsafe(40)
    csrf=secrets.token_urlsafe(32)
    now=int(time.time())
    with _pg() as db:
        db.execute('DELETE FROM vietframe_auth_sessions WHERE expires_at <= %s',(now,))
        db.execute("""INSERT INTO vietframe_auth_sessions
          (token_hash,user_id,csrf,expires_at,created_at,last_seen_at)
          VALUES(%s,%s,%s,%s,%s,%s)""",
          (core._token_hash(token),user_id,csrf,now+core.SESSION_TTL,now,now))
    return token,csrf

def get_session(token):
    if not token or len(token)>256:
        return None
    now=int(time.time())
    with _pg() as db:
        row=db.execute("""SELECT s.token_hash,s.csrf,s.expires_at,u.id,u.email,s.last_seen_at
          FROM vietframe_auth_sessions s JOIN vietframe_owner_users u ON u.id=s.user_id
          WHERE s.token_hash=%s AND s.expires_at>%s""",(core._token_hash(token),now)).fetchone()
        if not row:
            return None
        refresh=(now-row[5])>=86400
        if refresh:
            db.execute("""UPDATE vietframe_auth_sessions SET expires_at=%s,last_seen_at=%s
              WHERE token_hash=%s""",(now+core.SESSION_TTL,now,row[0]))
    return {'token_hash':row[0],'csrf':row[1],'id':row[3],'email':row[4],
            'expires_at':now+core.SESSION_TTL if refresh else row[2],
            'refresh_cookie':refresh}

def revoke_session(token):
    if not token:
        return
    with _pg() as db:
        db.execute('DELETE FROM vietframe_auth_sessions WHERE token_hash=%s',(core._token_hash(token),))

def change_password(user_id,old_password,new_password):
    core.validate_password(new_password)
    with _pg() as db:
        row=db.execute('SELECT password_hash FROM vietframe_owner_users WHERE id=%s',(user_id,)).fetchone()
    if not row or not core.verify_password(old_password,row[0]):
        return False
    digest=core.hash_password(new_password)
    with _pg() as db:
        db.execute('UPDATE vietframe_owner_users SET password_hash=%s WHERE id=%s',(digest,user_id))
        db.execute('DELETE FROM vietframe_auth_sessions WHERE user_id=%s',(user_id,))
    return True

def reset_owner_password(new_password):
    digest=core.hash_password(new_password)
    with _pg() as db:
        row=db.execute('SELECT id FROM vietframe_owner_users WHERE id=1').fetchone()
        if not row:
            raise ValueError('Chưa có chủ sở hữu.')
        db.execute('UPDATE vietframe_owner_users SET password_hash=%s WHERE id=%s',(digest,row[0]))
        db.execute('DELETE FROM vietframe_auth_sessions WHERE user_id=%s',(row[0],))
