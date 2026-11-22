"""v0.15 regression: Free-tier ElevenLabs voice rights before any render starts."""
import io
from pathlib import Path
import httpx
import pytest

from app import db, jobs, elevenlabs_bridge as eleven
from tests.test_api import fake_video


def voice(voice_id, category, name):
    return {'id':voice_id,'category':category,'name':name,
            'free_api_candidate':category=='premade'}


@pytest.fixture()
def fake_free(monkeypatch):
    seen=[]
    def quota(characters):
        seen.append(characters)
        return {'remaining':6000,'required':characters,'tier':'free'}
    monkeypatch.setattr(eleven,'free_quota_available',quota)
    monkeypatch.setattr(eleven,'voices',lambda:[
        voice('default01','premade','Default voice'),
        voice('sontran2026','professional','Son Tran - Casual'),
        voice('community01','high_quality','Shared Library voice'),
    ])
    return seen


def test_voice_api_reports_candidate_flag_from_real_metadata(monkeypatch):
    monkeypatch.setattr(eleven,'_require_key',lambda:'FAKE_NOT_REAL')
    class Response:
        def json(self):
            return {'voices':[{'voice_id':'default01','name':'Default','category':'premade'},
                              {'voice_id':'sontran2026','name':'Son Tran','category':'professional'},
                              {'voice_id':'mystery01','name':'Unknown'}]}
    monkeypatch.setattr(eleven,'_request',lambda method,path,key,**kw:Response())
    choices=eleven.voices()
    assert choices[0]['free_api_candidate'] is True
    assert choices[1]['free_api_candidate'] is False
    assert choices[2]['free_api_candidate'] is False


def test_premade_voice_passes_read_only_free_preflight(fake_free):
    result=eleven.preflight_free_voices(['default01'],120)
    assert result['eligible'] is True
    assert result['remaining']==6000 and result['required']==120
    assert result['voices_checked']==1
    assert fake_free==[120]


@pytest.mark.parametrize('restricted_id',['sontran2026','community01'])
def test_paid_library_voice_rejected_before_any_tts(fake_free,restricted_id):
    with pytest.raises(ValueError,match='API Free'):
        eleven.preflight_free_voices([restricted_id],150)


def test_mixed_speakers_rejects_second_paid_voice(fake_free):
    with pytest.raises(ValueError,match='giọng'):
        eleven.preflight_free_voices(['default01','sontran2026'],220)


def test_unknown_voice_id_fails_closed(fake_free):
    with pytest.raises(ValueError,match='không còn trong danh sách'):
        eleven.preflight_free_voices(['deleted_voice'],200)


@pytest.mark.parametrize('invalid_ids',[[],[''],['?invalid'],[f'voice_{i}' for i in range(17)]])
def test_malformed_voice_ids_rejected_without_api_calls(fake_free,invalid_ids):
    with pytest.raises(ValueError,match='không hợp lệ'):
        eleven.preflight_free_voices(invalid_ids,100)
    assert fake_free==[]


def test_preflight_rejects_unverified_quota(monkeypatch):
    monkeypatch.setattr(eleven,'free_quota_available',lambda n:(_ for _ in ()).throw(ValueError('Không đủ quota Free')))
    with pytest.raises(ValueError,match='quota Free'):
        eleven.preflight_free_voices(['default01'],500)


def test_render_rejects_paid_voice_without_marking_project_error(client,monkeypatch,fake_free):
    p=client.post('/api/projects/upload',data={'license_confirmed':'true'},
       files={'file':('sample.mp4',io.BytesIO(fake_video()),'video/mp4')})
    assert p.status_code==201,p.text
    pid=p.json()['id']
    saved=client.put(f'/api/projects/{pid}/segments',
        json={'segments':[{'start':0.1,'end':0.9,'text':'Xin chào','voice_text':'Xin chào','speaker':'spk1'}]})
    assert saved.status_code==200,saved.text
    monkeypatch.setattr(eleven,'is_connected',lambda:{'connected':True})
    monkeypatch.setattr(jobs,'submit',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('No job should start')))
    response=client.post(f'/api/projects/{pid}/complete-video',
        json={'style':{},'voice_provider':'elevenlabs','voice':'sontran2026','voice_map':{}})
    assert response.status_code==422,response.text
    assert 'API Free' in str(response.json())
    unchanged=client.get(f'/api/projects/{pid}').json()
    assert unchanged['status']=='ready'
    assert unchanged['segments'][0]['text']=='Xin chào'
    assert unchanged['video_file']


def test_premium_speaker_map_rejected_before_render(client,monkeypatch,fake_free):
    p=client.post('/api/projects/upload',data={'license_confirmed':'true'},
       files={'file':('sample.mp4',io.BytesIO(fake_video()),'video/mp4')})
    pid=p.json()['id']
    client.put(f'/api/projects/{pid}/segments',json={'segments':[
        {'start':0.1,'end':0.9,'text':'Xin chào','speaker':'spk1'}]})
    monkeypatch.setattr(eleven,'is_connected',lambda:{'connected':True})
    response=client.post(f'/api/projects/{pid}/complete-video',
        json={'style':{},'voice_provider':'elevenlabs','voice':'default01',
              'voice_map':{'spk1':'sontran2026'}})
    assert response.status_code==422
    assert db.get(pid)['status']=='ready'


def test_job_checks_free_voice_before_opening_partial_files(monkeypatch,tmp_path,fake_free):
    monkeypatch.setattr(db,'get',lambda pid:{
        'id':pid,'video_file':'source.mp4','segments':[
            {'start':0.1,'end':1.1,'text':'Xin chào','voice_text':'Xin chào','speaker':'spk1'}
        ],'duration':3.0})
    monkeypatch.setattr(jobs,'path_for',lambda pid:tmp_path)
    monkeypatch.setattr(eleven,'synthesize',lambda *a: (_ for _ in ()).throw(
        AssertionError('TTS must not be called for a restricted Free voice')))
    with pytest.raises(ValueError,match='API Free'):
        jobs.dubbing('projectid','sontran2026','elevenlabs')
    assert not list(tmp_path.glob('voice-*.mp3'))


def test_ui_disables_non_free_voices_and_does_not_claim_tts_success():
    js=(Path(__file__).resolve().parents[1]/'static/app.js').read_text()
    html=(Path(__file__).resolve().parents[1]/'static/index.html').read_text()
    assert 'item.free_api_candidate===true' in js
    assert 'option.disabled=!allowed' in js
    assert 'BỊ KHÓA trên API Free' in js
    assert 'API ElevenLabs đã liên kết' in js
    assert 'Đã kết nối ElevenLabs thành công' not in js
    assert 'API Free' in html
