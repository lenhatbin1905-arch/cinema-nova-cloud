"""VietFrame v0.8: external Gemini mocked; media-processing stays real in other tests."""
import io
import json
import subprocess
from pathlib import Path

import httpx
import pytest

from app import gemini_bridge as gemini, elevenlabs_bridge as eleven, config, jobs, db
from app.subtitles import verify_segments, make_srt
from test_api import fake_video


def samples():
    return {'language':'en','segments':[
        {'start':0.0,'end':1.0,'text':'Chào buổi sáng!',
         'voice_text':'Chào buổi sáng!','source_text':'Good morning!',
         'speaker':'spk1','needs_review':False},
        {'start':1.1,'end':2.0,'text':'Tôi là Jack.',
         'voice_text':'Mình là Jack.','source_text':'I am Jack.',
         'speaker':'spk2','needs_review':False}], 'notes':'Hai người đối thoại'}


def test_normalizer_retains_original_voice_speaker_and_times():
    result=gemini.normalize_script(samples(),2.3)
    assert result['segments'][1]['speaker']=='spk2'
    assert result['segments'][1]['voice_text']=='Mình là Jack.'
    assert result['segments'][1]['text']=='Tôi là Jack.'
    assert result['segments'][1]['source_text']=='I am Jack.'
    assert result['review_count']==0
    assert 'Chào buổi sáng' in make_srt(result['segments'])
    assert verify_segments(result['segments'],2.3)==result['segments']


def test_normalizer_rejects_hallucinated_timing_and_nan():
    for start,end in [(-.1,1),(0,5.0),(float('nan'),1.0),(2,1),(0,float('inf'))]:
        sample=samples();sample['segments'][0].update(start=start,end=end)
        with pytest.raises(ValueError):gemini.normalize_script(sample,2.3)


def test_normalizer_flags_fast_voice_and_unknown_original():
    data=samples()
    data['segments'][0]['source_text']=''
    data['segments'][0]['voice_text']='Lời thoại này quá dài và không thể đọc được một cách chậm rãi trong một giây.'
    info=gemini.normalize_script(data,2.3)
    assert info['segments'][0]['needs_review'] is True
    assert info['review_count']==1


def test_normalizer_does_not_create_speech_from_empty_output():
    assert gemini.normalize_script({'segments':[]},5)['segments']==[]
    with pytest.raises(ValueError):gemini.normalize_script({'segments':None},5)
    with pytest.raises(ValueError):gemini.normalize_script({'segments':[{'start':0,'end':1,'text':'ok','speaker':'weird'}]},5)


def test_gemini_api_link_encrypted_in_db_and_can_disconnect(client,monkeypatch):
    class MockResp:
        status_code=200
        def json(self):return {'name':'models/gemini-3.5-flash-lite'}
    class MockClient:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,headers=None):
            assert headers['x-goog-api-key']=='test-key-gemini-123'
            assert url=='/v1beta/models/gemini-3.5-flash-lite'
            return MockResp()
    monkeypatch.setattr(gemini.httpx,'Client',MockClient)
    response=client.post('/api/integrations/gemini/link',json={'api_key':'test-key-gemini-123'})
    assert response.status_code==200,response.text
    assert response.json()['connected']
    with gemini._connect() as con:
        secret=con.execute("SELECT encrypted_key FROM provider_credentials WHERE provider='gemini'").fetchone()[0]
        assert b'test-key-gemini-123' not in secret
    assert client.get('/api/integrations/gemini').json()['connected']
    assert client.delete('/api/integrations/gemini').json()['connected']==False


def test_gemini_external_calls_blocked_without_login(client):
    client.post('/api/auth/logout',json={})
    assert client.get('/api/integrations/gemini').status_code==401
    assert client.post('/api/integrations/gemini/link',json={'api_key':'test-key-gemini-123'}).status_code==401


def test_gemini_script_route_rejects_without_credentials(client):
    data=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},files={'file':('a.mp4',io.BytesIO(data),'video/mp4')})
    assert up.status_code==201,up.text
    pid=up.json()['id']
    r=client.post(f'/api/projects/{pid}/gemini-script',json={})
    assert r.status_code==503
    assert client.get(f'/api/projects/{pid}').json()['status']=='ready'


def test_gemini_script_queued_and_speaker_fields_saved(client,monkeypatch):
    data=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},files={'file':('a.mp4',io.BytesIO(data),'video/mp4')})
    assert up.status_code==201,up.text
    pid=up.json()['id']
    monkeypatch.setattr(gemini,'status',lambda:{'connected':True})
    # Do not call external API. Validate queue and job persistence with a deterministic stub.
    monkeypatch.setattr(jobs,'submit',lambda pid,fn,*args:fn(pid,*args))
    monkeypatch.setattr(gemini,'analyze_video',lambda source,duration,progress=None:gemini.normalize_script(samples(),duration))
    r=client.post(f'/api/projects/{pid}/gemini-script',json={})
    assert r.status_code==202,r.text
    p=client.get(f'/api/projects/{pid}').json()
    assert p['status']=='ready'
    assert p['segments'][1]['voice_text']=='Mình là Jack.'
    assert p['segments'][1]['speaker']=='spk2'
    assert 'Jack.' in client.get(f'/api/projects/{pid}/subtitles.srt').text
    assert (config.PROJECTS_DIR/pid/'gemini-script-report.json').exists()
    # A user resaving the voice_text should preserve what TTS reads.
    p['segments'][0]['voice_text']='Xin chào anh!'
    saved=client.put(f'/api/projects/{pid}/segments',json={'segments':p['segments']})
    assert saved.status_code==200,saved.text
    assert saved.json()['segments'][0]['voice_text']=='Xin chào anh!'


def test_gemini_upload_url_must_remain_on_google(tmp_path,monkeypatch):
    video=tmp_path/'sample.mp4';video.write_bytes(b'0'*1700)
    class FakeResponse:
        status_code=200
        headers={'x-goog-upload-url':'https://evil.example.com/steal-video'}
    class FakeClient:
        def post(self,*a,**kw):return FakeResponse()
    with pytest.raises(ValueError,match='không thuộc máy chủ Google'):
        gemini._upload(FakeClient(),video,'fake-key')


def test_protected_voice_map_validation_does_not_lock_project(client,monkeypatch):
    video=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},files={'file':('a.mp4',io.BytesIO(video),'video/mp4')})
    pid=up.json()['id']
    assert client.put(f'/api/projects/{pid}/segments',json={'segments':[{'start':.1,'end':1.5,'text':'Xin chào'}]}).status_code==200
    r=client.post(f'/api/projects/{pid}/complete-video',json={'style':{},'voice_map':{'../../escape':'voice-123'}})
    assert r.status_code==422,r.text
    assert client.get(f'/api/projects/{pid}').json()['status']=='ready'


def test_voice_map_and_voice_text_sent_to_tts_once_per_segment(client,monkeypatch):
    video=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},files={'file':('a.mp4',io.BytesIO(video),'video/mp4')})
    pid=up.json()['id']
    segments=[{'start':0.1,'end':1.05,'text':'Chào!','voice_text':'Xin chào!','speaker':'spk1'},
              {'start':1.2,'end':2.05,'text':'Tạm biệt!','voice_text':'Tạm biệt nhé!','speaker':'spk2'}]
    assert client.put(f'/api/projects/{pid}/segments',json={'segments':segments}).status_code==200
    preflight_calls=[]
    def free_preflight(ids,characters):
        preflight_calls.append((ids,characters))
        assert ids == ['default','alternative'] and characters > 0
        return {'eligible':True,'tier':'free','remaining':999,'required':characters}
    monkeypatch.setattr(eleven,'preflight_free_voices',free_preflight)
    calls=[]
    def synthesize(phrase,voice,path):
        calls.append((phrase,voice))
        proc=subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=470:duration=0.38',
                             '-ar','24000','-ac','2',str(path)],capture_output=True,text=True,timeout=25)
        assert proc.returncode==0,proc.stderr
    monkeypatch.setattr(eleven,'synthesize',synthesize)
    jobs.dubbing(pid,'default',provider='elevenlabs',voice_map={'spk2':'alternative'})
    assert calls==[('Xin chào!','default'),('Tạm biệt nhé!','alternative')]
    assert len(preflight_calls)==1
    assert client.get(f'/api/projects/{pid}').json()['dub_file']=='dub.wav'


def test_gemini_free_tier_limits_and_validation(client,monkeypatch):
    # No paid model names, no automatic billing fallback.
    with pytest.raises(ValueError):gemini.link('test-key-gemini-123',model='gemini-3-pro')
    assert gemini.MAX_ANALYSIS_DURATION <= 180
    assert gemini.MAX_ANALYSIS_BYTES <= 60*1024*1024


def test_one_gemini_inline_generation_without_files_reference(tmp_path, monkeypatch):
    import base64
    video=tmp_path/'source.mp4'
    video.write_bytes(b'X'*3000)
    calls=[]
    def handler(req):
        calls.append((req.method,req.url.path))
        assert req.headers.get('x-goog-api-key')=='fake-gemini-free-key'
        assert req.method=='POST'
        assert req.url.path=='/v1beta/models/gemini-3.5-flash-lite:generateContent'
        payload=json.loads(req.content)
        pieces=payload['contents'][0]['parts']
        assert pieces[0]['inlineData']['mimeType']=='video/mp4'
        assert base64.b64decode(pieces[0]['inlineData']['data'])==b'X'*3000
        assert '2.30 seconds' in pieces[1]['text']
        assert 'speaker' in pieces[1]['text'] and 'voice_text' in pieces[1]['text']
        assert payload['generationConfig']['temperature']==0.15
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(samples(),ensure_ascii=False)}]}}]})
    transport=httpx.MockTransport(handler)
    real=httpx.Client
    monkeypatch.setattr(gemini.httpx,'Client',lambda **kwargs:real(transport=transport,**kwargs))
    monkeypatch.setattr(gemini,'_key_model',lambda:('fake-gemini-free-key','gemini-3.5-flash-lite'))
    result=gemini.analyze_video(video,2.3)
    assert len(result['segments'])==2
    assert calls==[('POST','/v1beta/models/gemini-3.5-flash-lite:generateContent')]


def test_voice_timing_report_endpoint_from_real_synthesis(client, monkeypatch):
    video=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true'},files={'file':('a.mp4',io.BytesIO(video),'video/mp4')})
    pid=up.json()['id']
    assert client.put(f'/api/projects/{pid}/segments',json={'segments':[
        {'start':0.15,'end':1.4,'text':'Xin chào','voice_text':'Chào anh','speaker':'spk1'}]}).status_code==200
    checks=[]
    def approve(ids,characters):
        checks.append((ids,characters))
        assert ids == ['voice01'] and characters > 0
        return {'eligible':True,'tier':'free','remaining':1000,'required':characters}
    monkeypatch.setattr(eleven,'preflight_free_voices',approve)
    def fake_synthesize(phrase,voice,out):
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=490:duration=0.9','-ar','24000','-ac','2',str(out)],check=True,timeout=25)
    monkeypatch.setattr(eleven,'synthesize',fake_synthesize)
    jobs.dubbing(pid,'voice01',provider='elevenlabs')
    assert len(checks)==1
    report=client.get(f'/api/projects/{pid}/voice-timing-report')
    assert report.status_code==200
    data=report.json()
    assert data['all_within_limit']
    assert data['segments'][0]['speaker']=='spk1'
    assert data['segments'][0]['speech_text']=='Chào anh'
    assert abs(data['segments'][0]['slot_seconds']-1.25)<0.05
