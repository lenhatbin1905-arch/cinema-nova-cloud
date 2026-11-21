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
    with TestClient(app) as c:
        yield c
