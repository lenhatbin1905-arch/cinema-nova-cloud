"""v0.14: Google transient failures are bounded and failed projects recover safely."""
import io
import json
import httpx
import pytest

from app import config, db, gemini_bridge as gemini, jobs
from tests.test_api import fake_video
from tests.test_v08_gemini_voice_timing import samples


def fake_client(monkeypatch, responses):
    calls=[]
    real=httpx.Client
    def handler(request):
        assert request.method=='POST'
        assert request.url.path=='/v1beta/models/gemini-3.5-flash-lite:generateContent'
        assert request.headers.get('x-goog-api-key')=='test-free-tier-key'
        body=json.loads(request.content)
        assert body['contents'][0]['parts'][0]['inlineData']['mimeType']=='video/mp4'
        calls.append(request.url.path)
        status=responses[min(len(calls)-1,len(responses)-1)]
        if status==200:
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(samples(),ensure_ascii=False)}]}}]})
        return httpx.Response(status,json={'error':{'code':status,'message':'Gemini overloaded'}})
    monkeypatch.setattr(gemini.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(gemini,'_key_model',lambda:('test-free-tier-key','gemini-3.5-flash-lite'))
    sleeps=[]
    monkeypatch.setattr(gemini.time,'sleep',lambda n:sleeps.append(n))
    return calls,sleeps


def video_file(tmp_path):
    video=tmp_path/'video.mp4'
    video.write_bytes(b'x'*3500)
    return video


def test_503_then_success_reuses_one_media_payload_and_backoff(tmp_path,monkeypatch):
    calls,sleeps=fake_client(monkeypatch,[503,503,200])
    progress=[]
    script=gemini.analyze_video(video_file(tmp_path),2.3,progress=lambda p,m:progress.append((p,m)))
    assert len(script['segments'])==2
    assert len(calls)==3
    assert sleeps==[2,4]
    assert any('thử lại' in m for _,m in progress)
    assert progress[-1][0]==97


def test_503_always_fails_after_three_calls_without_fake_subtitles(tmp_path,monkeypatch):
    calls,sleeps=fake_client(monkeypatch,[503,503,503])
    with pytest.raises(ValueError,match='sau 3 lần thử'):
        gemini.analyze_video(video_file(tmp_path),2.3)
    assert len(calls)==3
    assert sleeps==[2,4]


@pytest.mark.parametrize('code',[401,403,404,429,500])
def test_quota_auth_model_and_nontransient_errors_never_retry(tmp_path,monkeypatch,code):
    calls,sleeps=fake_client(monkeypatch,[code])
    with pytest.raises(ValueError):
        gemini.analyze_video(video_file(tmp_path),2.3)
    assert len(calls)==1
    assert sleeps==[]


def test_failed_project_retry_atomic_and_does_not_discard_existing_subtitles(client,monkeypatch):
    r=client.post('/api/projects/upload',data={'license_confirmed':'true'},
                  files={'file':('sample.mp4',io.BytesIO(fake_video()),'video/mp4')})
    assert r.status_code==201,r.text
    pid=r.json()['id']
    segments=[{'start':0.1,'end':1.1,'text':'Đây là câu đã được lưu.'}]
    saved=client.put(f'/api/projects/{pid}/segments',json={'segments':segments})
    assert saved.status_code==200,saved.text
    db.update(pid,status='error',progress=0,message='Gemini quá tải HTTP 503')
    monkeypatch.setattr(gemini,'status',lambda:{'connected':True})
    pending=[]
    monkeypatch.setattr(jobs,'submit',lambda pid,fn,*args:pending.append((pid,fn)))
    retry=client.post(f'/api/projects/{pid}/gemini-script',json={})
    assert retry.status_code==202,retry.text
    assert len(pending)==1
    current=client.get(f'/api/projects/{pid}').json()
    assert current['status']=='analyzing'
    assert current['segments'][0]['text']=='Đây là câu đã được lưu.'
    concurrent=client.post(f'/api/projects/{pid}/gemini-script',json={})
    assert concurrent.status_code==409
    assert len(pending)==1


def test_retry_rejects_source_removed_after_failed_job(client,monkeypatch):
    r=client.post('/api/projects/upload',data={'license_confirmed':'true'},
                  files={'file':('sample.mp4',io.BytesIO(fake_video()),'video/mp4')})
    pid=r.json()['id']
    db.update(pid,status='error',message='Gemini 503')
    p=db.get(pid)
    (config.PROJECTS_DIR/pid/p['video_file']).unlink()
    monkeypatch.setattr(gemini,'status',lambda:{'connected':True})
    response=client.post(f'/api/projects/{pid}/gemini-script',json={})
    assert response.status_code==409
    assert db.get(pid)['status']=='error'


def test_ui_retry_button_has_real_event_handler_and_only_errored_source():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text()
    js=(root/'static/app.js').read_text()
    assert 'id="retry-gemini-button"' in html
    assert "$('#retry-gemini-button').addEventListener('click',analyzeGeminiScript)" in js
    assert "p?.status==='error'&&p?.video_url" in js
    assert 'Refresh buttons on server status changes' in js
