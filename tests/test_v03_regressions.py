"""Regression gates for job coordination, exports, project recovery and input validation."""
import io
import math
import subprocess
from pathlib import Path
import pytest
from app import db, jobs, config
from app.subtitles import verify_segments, make_ass


def make_clip():
    proc=subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
       'color=c=#202e36:s=176x320:d=1.1:r=8','-c:v','libx264','-pix_fmt','yuv420p',
       '-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],
       capture_output=True,timeout=25)
    assert proc.returncode == 0,proc.stderr
    return proc.stdout


def new_project(client):
    r=client.post('/api/projects/upload',data={'license_confirmed':'true','title':'Kiểm thử'},
                  files={'file':('clip.mp4',io.BytesIO(make_clip()),'video/mp4')})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_double_click_render_is_atomically_rejected(client,monkeypatch):
    pid=new_project(client)
    url=f'/api/projects/{pid}'
    assert client.put(url+'/segments',json={'segments':[{'start':0.0,'end':1.0,'text':'Chào Việt Nam'}]}).status_code==200
    calls=[]
    monkeypatch.setattr(jobs,'submit',lambda *args:calls.append(args))
    a=client.post(url+'/render',json={})
    b=client.post(url+'/render',json={})
    assert a.status_code==202
    assert b.status_code==409
    assert len(calls)==1
    assert client.get(url).json()['status']=='rendering'
    assert client.put(url+'/segments',json={'segments':[]}).status_code==409


def test_save_same_segments_preserves_dub_and_export(client):
    pid=new_project(client)
    url=f'/api/projects/{pid}'
    body={'segments':[{'start':0,'end':1,'text':'Giọng Việt'}]}
    assert client.put(url+'/segments',json=body).status_code==200
    db.update(pid,dub_file='dub.wav',output_file='export.mp4')
    assert client.put(url+'/segments',json=body).status_code==200
    p=client.get(url).json()
    assert p['dub_file']=='dub.wav'
    assert p['output_file']=='export.mp4'
    assert client.put(url+'/segments',json={'segments':[{'start':0,'end':1,'text':'Giọng mới'}]}).status_code==200
    p=client.get(url).json()
    assert p['dub_file'] is None and p['output_file'] is None


def test_restart_marks_pending_jobs_and_recovers_when_video_exists(client):
    pid=new_project(client)
    db.update(pid,status='rendering',progress=22)
    db.mark_interrupted_jobs()
    p=client.get(f'/api/projects/{pid}').json()
    assert p['status']=='error' and 'gián đoạn' in p['message']
    r=client.post(f'/api/projects/{pid}/recover')
    assert r.status_code==200,r.text
    assert r.json()['status']=='ready'
    assert client.post(f'/api/projects/{pid}/recover').status_code==409


def test_cannot_recover_unimported_link(client,monkeypatch):
    monkeypatch.setattr(jobs,'submit',lambda *args:None)
    p=client.post('/api/projects/from-url',json={'url':'https://youtu.be/abc','license_confirmed':True}).json()
    db.update(p['id'],status='error',message='Link không tải được')
    assert client.post(f'/api/projects/{p["id"]}/recover').status_code==409


def test_response_security_headers_and_version(client):
    response=client.get('/')
    assert response.headers['X-Frame-Options']=='DENY'
    assert 'object-src' in response.headers['Content-Security-Policy']
    assert response.headers['X-Content-Type-Options']=='nosniff'
    assert client.get('/api/health').json()['version']=='0.13.0'
    assert client.get('/api/projects').headers['Cache-Control']=='no-store'


def test_reject_nan_and_control_characters():
    with pytest.raises(ValueError):
        verify_segments([{'start':math.nan,'end':3,'text':'OK'}])
    with pytest.raises(ValueError):
        verify_segments([{'start':0,'end':math.inf,'text':'OK'}])
    cleaned=verify_segments([{'start':0,'end':1,'text':'Hi\x00\x01\r\nViệt Nam'}])
    assert cleaned[0]['text']=='Hi\nViệt Nam'
    rendered=make_ass(cleaned,{},resolution=(576,1024))
    assert 'PlayResX: 576' in rendered and 'PlayResY: 1024' in rendered


def test_atomic_export_does_not_publish_invalid_temp(tmp_path,monkeypatch):
    from app import media
    source=tmp_path/'source.mp4'; ass=tmp_path/'subtitles.ass'; export=tmp_path/'export.mp4'
    source.write_bytes(b'bad source'); ass.write_text('broken'); export.write_bytes(b'LAST_GOOD_EXPORT')
    with pytest.raises(RuntimeError):
        media.ffmpeg_render(source,ass,export)
    assert export.read_bytes()==b'LAST_GOOD_EXPORT'
    assert not (tmp_path/'export.partial.mp4').exists()


def test_no_public_auth_claim(client):
    # Single owner is protected, but public-hosting hardening is still required.
    assert config.MAX_UPLOAD_MB > 0
    assert client.get('/api/health').json()['mode']=='local-first'
    assert client.get('/api/auth/me').status_code==200
