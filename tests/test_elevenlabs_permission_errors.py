"""Scoped ElevenLabs API keys must report missing permissions without leaking secrets."""
import pytest
import httpx
from app import elevenlabs_bridge as eleven


class FakeClient:
    def __init__(self, status, body):
        self.status = status
        self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def request(self, *args, **kwargs):
        return httpx.Response(self.status, json=self.body,
                              request=httpx.Request('GET', 'https://api.elevenlabs.io/v1/user'))


@pytest.mark.parametrize('permission,label', [
    ('user_read', 'User → Read'),
    ('voices_read', 'Voices → Read'),
    ('text_to_speech', 'Text to Speech → Access'),
])
def test_missing_api_scope_names_permission(permission, label, monkeypatch):
    monkeypatch.setattr(eleven.httpx, 'Client', lambda **kw: FakeClient(401, {
        'detail': {'status':'missing_permissions', 'message': 'The API key you used is missing the permission ' + permission}
    }))
    with pytest.raises(ValueError, match=label):
        eleven._request('GET', '/v1/user', 'test-only-key')


def test_auth_error_does_not_leak_api_key(monkeypatch):
    monkeypatch.setattr(eleven.httpx, 'Client', lambda **kw: FakeClient(403, {'detail': 'Unauthorized'}))
    with pytest.raises(ValueError) as exc:
        eleven._request('GET', '/v1/user', 'secret-do-not-log')
    assert 'secret-do-not-log' not in str(exc.value)
