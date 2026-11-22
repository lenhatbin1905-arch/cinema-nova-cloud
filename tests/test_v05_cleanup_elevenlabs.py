import io
import sqlite3
import subprocess
import time
import pytest
from app import config, db, elevenlabs_bridge as eleven, cleanup, jobs
from tests.test_api import fake_video


def test_cleanup_rejects_out_of_bounds_and_injection():
    assert cleanup.filter_chain([{'x':10,'y':70,'w':80,'h':8,'method':'edge'}],320,570)==['delogo=x=32:y=399:w=256:h=46:show=0']
    assert cleanup.filter_chain([{'x':70,'y':4,'w':20,'h':8,'method':'edge'}],540,960)[0].startswith('delogo=x=378:y=38:w=108')
    for bad in [[{'x':90,'y':80,'w':30,'h':30}], [{'x':0,'y':0,'w':1,'h':20}], [{'x':4,'y':70,'w':92,'h':15}], [{}],
                [{'x':0,'y':0,'w':10,'h':10}]*81]:
        with pytest.raises((ValueError,KeyError,TypeError)):
            cleanup.validate_regions(bad)


def test_cleanup_authenticated_and_real_ffmpeg(client):
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},
        files={'file':('film.mp4',io.BytesIO(fake_video()),'video/mp4')})
    assert up.status_code==201,up.text
    pid=up.json()['id']
    assert client.put(f'/api/projects/{pid}/cleanup',json={'regions':[{'x':4,'y':70,'w':90,'h':8,'method':'edge','start':0.2,'end':1.7}]}).status_code==200
    assert client.get(f'/api/projects/{pid}').json()['cleanup_regions']==[{'x':4,'y':70,'w':90,'h':8,'method':'edge','start':0.2,'end':1.7}]
    assert client.put(f'/api/projects/{pid}/cleanup',json={'regions':[{'x':95,'y':80,'w':20,'h':20}]}).status_code==422
    assert client.put(f'/api/projects/{pid}/segments',json={'segments':[{'start':.2,'end':1.7,'text':'Phụ đề Việt thay chữ gốc.'}]}).status_code==200
    # Real FFmpeg filter graph: delogo -> ASS subtitle, then valid MP4.
    jobs.render(pid,{'font':'DejaVu Sans','font_size':29,'color':'#FFDD22','outline_color':'#000000','outline':2,'bold':True,'margin_v':54})
    result=client.get(f'/api/projects/{pid}').json()
    assert result['output_file']=='export.mp4',result
    assert client.get(result['export_url']).status_code==200
    assert (config.PROJECTS_DIR/pid/'export.mp4').stat().st_size>3000
    assert client.put(f'/api/projects/{pid}/cleanup',json={'regions':[]}).status_code==200
    assert client.get(f'/api/projects/{pid}').json()['output_file'] is None


def test_elevenlabs_link_encrypt_quota_and_disconnect(client,monkeypatch):
    class Resp:
        def __init__(self,data):self.data=data
        def json(self):return self.data
    def fake_request(method,path,key,**kw):
        assert key=='test-provider-api-key-123456789'
        if path=='/v1/user': return Resp({'email':'linked@example.org'})
        if path=='/v2/voices': return Resp({'voices':[{'voice_id':'abcDEF_123', 'name':'Vietnamese'}]})
        if path=='/v1/user/subscription': return Resp({'tier':'free','character_limit':10000,'character_count':9500})
        raise AssertionError(path)
    monkeypatch.setattr(eleven,'_request',fake_request)
    state=client.get('/api/integrations/elevenlabs').json()
    assert state['connected'] is False and state['label'] is None
    assert 'storage' in state and 'api_key' not in state
    assert client.get('/api/integrations/elevenlabs/voices').status_code==422
    link=client.post('/api/integrations/elevenlabs/link',json={'api_key':'test-provider-api-key-123456789'})
    assert link.status_code==200,link.text
    assert link.json()=={'connected':True,'label':'linked@example.org'}
    assert client.get('/api/integrations/elevenlabs/voices').json()['voices'][0]['name']=='Vietnamese'
    with sqlite3.connect(config.DB_PATH) as conn:
        cipher=conn.execute("SELECT encrypted_key FROM provider_credentials WHERE provider='elevenlabs'").fetchone()[0]
    assert b'test-provider-api-key-123456789' not in cipher
    assert 'api_key' not in client.get('/api/integrations/elevenlabs').text
    assert eleven._get_key()=='test-provider-api-key-123456789'
    assert eleven.free_quota_available(100)['remaining']==500
    with pytest.raises(ValueError,match='không đủ'):
        eleven.free_quota_available(600)
    assert client.request('DELETE','/api/integrations/elevenlabs').json()=={'connected':False}
    assert eleven._get_key() is None


def test_provider_auth_csrf_and_no_paid_quota(client,monkeypatch):
    # Unauthenticated request never sees connection state.
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anon:
        assert anon.get('/api/integrations/elevenlabs').status_code==401
        assert anon.post('/api/integrations/elevenlabs/link',json={'api_key':'x'*32}).status_code==401
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/integrations/elevenlabs/link',json={'api_key':'x'*32}).status_code==403
    # Only free tier is allowed: paid account cannot silently incur costs.
    monkeypatch.setattr(eleven,'_require_key',lambda:'test-secret')
    class Resp:
        def json(self):return {'tier':'starter','character_limit':20000,'character_count':0}
    monkeypatch.setattr(eleven,'_request',lambda *a,**kw: Resp())
    with pytest.raises(ValueError,match='Free-First'):
        eleven.free_quota_available(30)


def test_elevenlabs_audio_pipeline_mocked_not_quality_claim(client,monkeypatch):
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},files={'file':('film.mp4',io.BytesIO(fake_video()),'video/mp4')})
    pid=up.json()['id']
    client.put(f'/api/projects/{pid}/segments',json={'segments':[{'start':0.2,'end':1.8,'text':'Xin chào từ ElevenLabs.'}]})
    monkeypatch.setattr(eleven,'free_quota_available',lambda characters:{'tier':'free','remaining':1000,'required':characters})
    monkeypatch.setattr(eleven,'is_connected',lambda:{'connected':True,'label':'test'})
    def fake_synth(text,voice,filename):
        proc=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','sine=frequency=520:duration=0.9','-c:a','libmp3lame',str(filename)],capture_output=True,text=True,timeout=25)
        assert proc.returncode==0,proc.stderr
    monkeypatch.setattr(eleven,'synthesize',fake_synth)
    jobs.dubbing(pid,'abc123_456','elevenlabs')
    project=client.get('/api/projects/'+pid).json()
    assert project['dub_file']=='dub.wav'
    assert client.get(project['dub_url']).status_code==200
    # This is synthetic sine wave audio; does NOT validate natural ElevenLabs voice.
