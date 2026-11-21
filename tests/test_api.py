import io
import subprocess
from app import config, db


def fake_video():
    proc=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=#0f2d26:s=320x570:d=2.3:r=12',
                          '-f','lavfi','-i','sine=frequency=430:duration=2.3',
                          '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',
                          '-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],capture_output=True,timeout=30)
    assert proc.returncode==0,proc.stderr
    return proc.stdout


def test_home_health_and_free_capability(client):
    assert client.get('/').status_code==200
    assert 'VietFrame Studio' in client.get('/').text
    assert client.get('/api/health').json()['status']=='ok'
    caps=client.get('/api/capabilities').json()
    assert 'platforms' in caps and len(caps['platforms'])==6
    assert caps['ffmpeg']


def test_disallow_unlicensed_import(client):
    r=client.post('/api/projects/from-url',json={'url':'https://youtu.be/hello','license_confirmed':False})
    assert r.status_code==422
    r=client.post('/api/projects/from-url',json={'url':'https://youtube.com.evil.org/watch','license_confirmed':True})
    assert r.status_code==422
    assert client.get('/api/projects').json()==[]


def test_invalid_video_upload(client):
    resp=client.post('/api/projects/upload',data={'license_confirmed':'true'},
        files={'file':('notvideo.mp4',b'this is not a video','video/mp4')})
    assert resp.status_code==422
    assert client.get('/api/projects').json()==[]


def test_upload_subtitles_render_real_mp4(client):
    data=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true','title':'Video kiểm thử'},
        files={'file':('film.mp4',io.BytesIO(data),'video/mp4')})
    assert up.status_code==201,up.text
    p=up.json();pid=p['id']
    assert p['status']=='ready' and 2 <= p['duration'] < 3
    assert client.get(p['video_url']).status_code==200
    segments=[{'start':0.1,'end':1.1,'text':'Xin chào Việt Nam!'},{'start':1.1,'end':2.1,'text':'Một video thật.'}]
    saved=client.put(f'/api/projects/{pid}/segments',json={'segments':segments})
    assert saved.status_code==200,saved.text
    assert 'Xin chào' in client.get(f'/api/projects/{pid}/subtitles.srt').text
    result=client.post(f'/api/projects/{pid}/render',json={'font':'DejaVu Sans','color':'#FFCC22'})
    assert result.status_code==202,result.text
    # Await local job result using bounded client polling, never fake it.
    import time
    deadline=time.time()+45
    while time.time()<deadline:
        p=client.get(f'/api/projects/{pid}').json()
        if p['status'] in ('ready','error') and p['output_file']:
            break
        if p['status']=='error':
            raise AssertionError(p['message'])
        time.sleep(.15)
    assert p['output_file']=='export.mp4' and p['status']=='ready',p
    result=client.get(p['export_url'])
    assert result.status_code==200
    assert len(result.content)>1000
    file=config.PROJECTS_DIR/pid/'export.mp4'
    check=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(file)],capture_output=True,text=True)
    assert check.returncode==0 and float(check.stdout)>1.8
    assert client.get(f'/api/projects/{pid}/reference-style').status_code==200


def test_no_path_traversal(client):
    assert client.get('/api/projects/../../etc/passwd/file/source').status_code in [404,307]
    assert client.get('/api/projects/not-a-real-id/file/export').status_code==404


def test_kokoro_dub_pipeline_with_synthesized_tone(client, monkeypatch, tmp_path):
    from app import engines, jobs
    data=fake_video()
    up=client.post('/api/projects/upload',data={'license_confirmed':'true','title':'Kokoro audio test'},
        files={'file':('test.mp4',io.BytesIO(data),'video/mp4')})
    assert up.status_code==201
    pid=up.json()['id']
    assert client.put(f'/api/projects/{pid}/segments',json={'segments':[{'start':0.3,'end':1.8,'text':'Xin chào!'}]}).status_code==200
    # Stand-in WAV is generated with FFmpeg, NOT claimed as actual Kokoro quality.
    def fake_synthesize(text,voice,path):
        output=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-y',
            '-f','lavfi','-i','sine=frequency=560:duration=0.85',
            '-ar','24000','-ac','2',str(path)],capture_output=True,text=True,timeout=20)
        assert output.returncode==0,output.stderr
        return path
    monkeypatch.setattr(engines,'kokoro_is_ready',lambda: True)
    monkeypatch.setattr(engines,'kokoro_synthesize',fake_synthesize)
    jobs.dubbing(pid,'vi_test_voice')
    p=client.get(f'/api/projects/{pid}').json()
    assert p['status']=='ready' and p['dub_file']=='dub.wav',p
    wav=client.get(p['dub_url'])
    assert wav.status_code==200 and len(wav.content)>2000
    jobs.render(pid,{'font':'DejaVu Sans'})
    p=client.get(f'/api/projects/{pid}').json()
    assert p['status']=='ready' and p['output_file']=='export.mp4',p
    file=config.PROJECTS_DIR/pid/'export.mp4'
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(file)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and float(result.stdout)>2.2


def test_dubbing_not_faked_without_voice_engine(client):
    assert client.get('/api/voices').status_code==503
