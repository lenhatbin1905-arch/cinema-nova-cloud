import json
import sqlite3
from datetime import datetime, timezone
from .config import DB_PATH


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=30000')
    return con


def init_db():
    with _connect() as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('''CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
          source_url TEXT, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
          message TEXT NOT NULL DEFAULT '', video_file TEXT, output_file TEXT,
          segments_json TEXT NOT NULL DEFAULT '[]', duration REAL DEFAULT 0, dub_file TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )''')
        cols={r[1] for r in con.execute('PRAGMA table_info(projects)').fetchall()}
        if 'dub_file' not in cols:
            con.execute('ALTER TABLE projects ADD COLUMN dub_file TEXT')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def create(project_id, title, source, source_url=None, status='queued'):
    timestamp = now()
    with _connect() as con:
        con.execute('''INSERT INTO projects
        (id,title,source,source_url,status,progress,message,created_at,updated_at)
        VALUES(?,?,?,?,?,0,'',?,?)''',
        (project_id, title[:140], source, source_url, status, timestamp, timestamp))
    return get(project_id)


def update(project_id, **fields):
    if not fields:
        return
    allowed = {'title', 'status', 'progress', 'message', 'video_file', 'output_file', 'segments_json', 'duration', 'dub_file'}
    invalid = set(fields) - allowed
    if invalid:
        raise ValueError('Unknown fields: ' + ','.join(sorted(invalid)))
    fields['updated_at'] = now()
    keys = list(fields)
    with _connect() as con:
        con.execute('UPDATE projects SET '+', '.join(f'{k}=?' for k in keys)+' WHERE id=?',
                    [fields[k] for k in keys] + [project_id])


def get(project_id):
    with _connect() as con:
        row = con.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    return _asdict(row) if row else None


def all_projects():
    with _connect() as con:
        rows = con.execute('SELECT * FROM projects ORDER BY created_at DESC LIMIT 200').fetchall()
    return [_asdict(r) for r in rows]


def _asdict(row):
    obj = dict(row)
    obj['segments'] = json.loads(obj.pop('segments_json'))
    return obj
