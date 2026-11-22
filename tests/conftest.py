import pytest
from fastapi.testclient import TestClient
from app import config,db
from app.main import app


@pytest.fixture
def client(tmp_path,monkeypatch):
    project_dir=tmp_path/'projects'
    project_dir.mkdir()
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    monkeypatch.setattr(config,'PROJECTS_DIR',project_dir)
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'test.sqlite3')
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'test.sqlite3')
    monkeypatch.setattr(config,'SETUP_TOKEN','local-test-setup-key')
    monkeypatch.setattr(config,'COOKIE_SECURE',False)
    with TestClient(app) as c:
        result = c.post('/api/auth/setup',json={'email':'owner@example.com','password':'only-for-local-test-phrase-123','setup_token':'local-test-setup-key'})
        assert result.status_code == 201, result.text
        c.headers.update({'X-CSRF-Token': result.json()['csrf']})
        yield c
