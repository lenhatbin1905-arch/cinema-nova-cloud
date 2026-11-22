"""v0.11: server-confirmed progress milestones and scoped provider keys."""
from pathlib import Path
import httpx
import pytest
from app import db, elevenlabs_bridge as eleven, gemini_bridge as gemini


def test_scoped_eleven_key_can_link_for_voice_selection_but_quota_stays_locked(client, monkeypatch):
    class Resp:
        def __init__(self, obj): self.obj=obj
        def json(self): return self.obj
    def fake_request(method, path, key, **kwargs):
        if path == '/v1/user':
            raise ValueError('API key ElevenLabs thiếu quyền: User → Read')
        if path == '/v2/voices':
            return Resp({'voices': [{'voice_id':'vnvoice123','name':'Vietnamese'}]})
        if path == '/v1/user/subscription':
            raise ValueError('API key ElevenLabs thiếu quyền: User → Read')
        raise AssertionError(path)
    monkeypatch.setattr(eleven,'_request',fake_request)
    key='scoped-elevenlabs-key-123456789'
    result=client.post('/api/integrations/elevenlabs/link',json={'api_key':key})
    assert result.status_code==200,result.text
    assert result.json()['connected'] and result.json()['limited']
    assert 'User → Read' in result.json()['warning']
    state=client.get('/api/integrations/elevenlabs').json()
    assert state['limited'] and 'User → Read' in state['warning']
    voice=client.get('/api/integrations/elevenlabs/voices')
    assert voice.status_code==200 and voice.json()['voices'][0]['name']=='Vietnamese'
    with pytest.raises(ValueError,match='User → Read'):
        eleven.free_quota_available(10)
    assert key not in client.get('/api/integrations/elevenlabs').text


def test_bad_eleven_key_is_never_saved(client, monkeypatch):
    def invalid(*args,**kwargs):
        raise ValueError('API key bị từ chối')
    monkeypatch.setattr(eleven,'_request',invalid)
    r=client.post('/api/integrations/elevenlabs/link',json={'api_key':'invalid-eleven-key-123456789'})
    assert r.status_code==422
    assert client.get('/api/integrations/elevenlabs').json()['connected'] is False


def test_gemini_progress_callbacks_are_real_phase_completions(tmp_path,monkeypatch):
    from tests.test_v08_gemini_voice_timing import samples
    video=tmp_path/'video.mp4';video.write_bytes(b'X'*3500)
    phases=[]
    def responder(req):
        if req.method=='POST' and req.url.path=='/v1beta/models/gemini-3.5-flash-lite:generateContent':
            import json,base64
            payload=json.loads(req.content)
            assert base64.b64decode(payload['contents'][0]['parts'][0]['inlineData']['data'])==b'X'*3500
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(samples())}]}}]})
        raise AssertionError((req.method,req.url.path))
    real=httpx.Client
    monkeypatch.setattr(gemini.httpx,'Client',lambda **k:real(transport=httpx.MockTransport(responder),**k))
    monkeypatch.setattr(gemini,'_key_model',lambda:('local-test-fake-key','gemini-3.5-flash-lite'))
    result=gemini.analyze_video(video,2.3,progress=lambda n,msg:phases.append((n,msg)))
    assert len(result['segments'])==2
    assert [n for n,_ in phases]==[11,31,55,74,91,97]
    assert all(phases[i][0]<phases[i+1][0] for i in range(len(phases)-1))
    assert 'phụ đề' in phases[-1][1]


def test_progress_widget_is_visible_above_player_and_not_a_fake_timer():
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text()
    js=(root/'static/app.js').read_text()
    assert html.index('id="job-progress"')<html.index('id="player"')
    assert 'role="progressbar"' in html and 'aria-valuenow="0"' in html
    assert 'renderJobProgress(p);' in js
    assert 'Gemini xử lý' in js
    assert 'id="gemini-prerequisite"' in html
    assert "$('#gemini-prerequisite').classList.toggle" in js
    assert 'setInterval' not in js[js.index('function renderJobProgress'):js.index('function showProject')]
    assert 'tác vụ' in js and "project.status==='error'" in js


def test_error_display_and_missing_video_are_not_marked_complete():
    js=Path(__file__).resolve().parents[1]/'static/app.js'
    src=js.read_text()
    assert "failed?0:active?" in src
    assert "text($('#job-percent'),failed?'Có lỗi'" in src
    assert "panel.classList.toggle('failed',failed)" in src
