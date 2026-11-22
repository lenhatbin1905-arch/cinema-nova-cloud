"""Encrypted provider-key storage: Neon Postgres in hosted mode, SQLite locally.

The encryption key remains in a Render secret environment variable. Never log
connection strings, Fernet ciphertext, or API key values. All writes are atomic.
"""
import os
import sqlite3
from . import config

def persistent():
    return bool(os.environ.get('VIETFRAME_CREDENTIALS_DATABASE_URL', '').strip())

def kind():
    return 'Neon Postgres · lưu bền vững' if persistent() else 'SQLite trên máy chủ · có thể mất khi triển khai lại'

def _require_storage():
    if not persistent() and os.environ.get('VIETFRAME_REQUIRE_PERSISTENT_KEYS','').strip().lower() == 'true':
        raise RuntimeError('Máy chủ chưa có kho lưu API key bền vững. Không được lưu khóa vào ổ đĩa tạm.')

def _pg():
    import psycopg
    return psycopg.connect(os.environ['VIETFRAME_CREDENTIALS_DATABASE_URL'].strip(),
                           connect_timeout=15, sslmode='require')

def init():
    _require_storage()
    if persistent():
        with _pg() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS vietframe_provider_credentials (
                provider TEXT PRIMARY KEY,
                encrypted_key BYTEA NOT NULL,
                account_label TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
    else:
        with sqlite3.connect(config.DB_PATH) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS provider_credentials (
                provider TEXT PRIMARY KEY, encrypted_key BLOB NOT NULL,
                account_label TEXT NOT NULL DEFAULT ''
            )""")

def get(provider):
    _require_storage()
    if provider not in ('gemini','elevenlabs'):
        raise ValueError('Dịch vụ không được phép.')
    if persistent():
        with _pg() as db:
            row=db.execute('SELECT encrypted_key, account_label FROM vietframe_provider_credentials WHERE provider=%s', (provider,)).fetchone()
            return (bytes(row[0]), row[1]) if row else None
    with sqlite3.connect(config.DB_PATH) as db:
        return db.execute('SELECT encrypted_key, account_label FROM provider_credentials WHERE provider=?', (provider,)).fetchone()

def save(provider, encrypted_key, label):
    _require_storage()
    if provider not in ('gemini','elevenlabs'):
        raise ValueError('Dịch vụ không được phép.')
    if persistent():
        with _pg() as db:
            db.execute("""INSERT INTO vietframe_provider_credentials(provider,encrypted_key,account_label)
              VALUES (%s,%s,%s) ON CONFLICT (provider) DO UPDATE SET
              encrypted_key=EXCLUDED.encrypted_key,account_label=EXCLUDED.account_label,updated_at=NOW()""",
              (provider,bytes(encrypted_key),label[:120]))
    else:
        with sqlite3.connect(config.DB_PATH) as db:
            db.execute('INSERT OR REPLACE INTO provider_credentials(provider,encrypted_key,account_label) VALUES (?,?,?)',
                       (provider,encrypted_key,label[:120]))

def delete(provider):
    _require_storage()
    if provider not in ('gemini','elevenlabs'):
        raise ValueError('Dịch vụ không được phép.')
    if persistent():
        with _pg() as db:
            db.execute('DELETE FROM vietframe_provider_credentials WHERE provider=%s',(provider,))
    else:
        with sqlite3.connect(config.DB_PATH) as db:
            db.execute('DELETE FROM provider_credentials WHERE provider=?',(provider,))
