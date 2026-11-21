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


def claim_ready_project(project_id, status, message):
    """Atomically claim a job. Two rapid clicks cannot start competing renders."""
    with _connect() as con:
        row = con.execute(
            "UPDATE projects SET status=?, progress=1, message=?, output_file=CASE WHEN ?='rendering' THEN NULL ELSE output_file END, updated_at=? "
            "WHERE id=? AND status='ready' RETURNING id",
            (status, message, status, now(), project_id),
        ).fetchone()
        return row is not None


def save_segments_if_ready(project_id, segments):
    """Keep finished dubbing when captions are unchanged; invalidate derived media on edits."""
    encoded = json.dumps(segments, ensure_ascii=False)
    with _connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT status, segments_json FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row or row['status'] != 'ready':
            return False, False
        if json.loads(row['segments_json']) == segments:
            return True, False
        con.execute('UPDATE projects SET segments_json=?, output_file=NULL, dub_file=NULL, '
                    'message=?, updated_at=? WHERE id=?',
                    (encoded, 'Đã lưu phụ đề mới; cần xuất lại MP4 và giọng đọc.', now(), project_id))
        return True, True


def mark_interrupted_jobs():
    """On restart report jobs lost by the in-process executor; never leave fake progress."""
    with _connect() as con:
        con.execute("UPDATE projects SET status='error', progress=0, "
                    "message='Tác vụ bị gián đoạn do máy chủ khởi động lại. Có thể khôi phục dự án nếu video nguồn còn.', "
                    "updated_at=? WHERE status IN ('queued','downloading','transcribing','translating','rendering','dubbing','generating')",
                    (now(),))


def recover_project(project_id):
    """Recover an interrupted/failed project when an importable source file exists."""
    with _connect() as con:
        changed=con.execute("UPDATE projects SET status='ready', progress=100, message=?, updated_at=? "
                            "WHERE id=? AND status='error' AND video_file IS NOT NULL",
                            ('Đã khôi phục để tiếp tục biên tập. Kiểm tra lại nội dung trước khi xuất.', now(),project_id))
        return bool(changed.rowcount)
