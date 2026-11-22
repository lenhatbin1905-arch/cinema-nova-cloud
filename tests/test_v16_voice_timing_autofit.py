"""Real FFmpeg tests for automatic Vietnamese dubbing timing correction.

No ElevenLabs/Gemini API credit is consumed. Audio is an actual local sine
wave; MP4 output is encoded and inspected with ffprobe.
"""
import io
import json
import math
import subprocess

import pytest

from app import config, db, jobs, elevenlabs_bridge as eleven
from tests.test_api import fake_video


@pytest.mark.parametrize('rate',[1.0,1.35,1.6,1.95,2.6,3.0])
def test_tempo_filter_preserves_requested_rate_with_safe_stages(rate):
    expression=jobs.tempo_filter(rate)
    stages=[float(x.split('=')[1]) for x in expression.split(',')]
    assert len(stages)>=1
    assert all(0.5<=n<=2.0 for n in stages)
    assert math.isclose(math.prod(stages),rate,rel_tol=1e-5)
    if rate<=2: assert len(stages)==1


@pytest.mark.parametrize('rate',[float('nan'),float('inf'),float('-inf'),0,-1])
def test_tempo_filter_rejects_invalid_speeds(rate):
    with pytest.raises(ValueError,match='không hợp lệ'):
        jobs.tempo_filter(rate)


def _new_project(client):
    result=client.post('/api/projects/upload',
        data={'license_confirmed':'true'},
        files={'file':('video.mp4',io.BytesIO(fake_video()),'video/mp4')})
    assert result.status_code==201,result.text
    pid=result.json()['id']
    saved=client.put(f'/api/projects/{pid}/segments',json={'segments':[
        {'start':0.15,'end':1.15,'text':'Đây là phụ đề tiếng Việt không bị xóa.',
         'voice_text':'Đây là lời thoại tiếng Việt dùng để lồng tiếng.','speaker':'spk1'}]})
    assert saved.status_code==200,saved.text
    return pid


def _mock_tts(monkeypatch,length):
    produced=[]
    preflights=[]
    def synthesize(speech,voice,filename):
        produced.append((speech,voice))
        result=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-y',
            '-f','lavfi','-i',f'sine=frequency=465:duration={length:.3f}',
            '-ar','24000','-ac','2',str(filename)],
            capture_output=True,text=True,timeout=25)
        assert result.returncode==0,result.stderr
        return filename
    def preflight(ids,characters):
        preflights.append((ids,characters))
        assert ids==['voice01'] and characters>0
        return {'eligible':True,'tier':'free','remaining':5000,'required':characters}
    monkeypatch.setattr(eleven,'synthesize',synthesize)
    monkeypatch.setattr(eleven,'preflight_free_voices',preflight)
    return produced,preflights


def _duration(path):
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
      '-of','default=nk=1:nw=1',str(path)],
      capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    return float(result.stdout.strip())


def test_160_percent_speech_now_dubs_and_renders_real_mp4(client,monkeypatch):
    pid=_new_project(client)
    produced,preflights=_mock_tts(monkeypatch,1.60)
    jobs.complete_video(pid,{'font':'DejaVu Sans'},'elevenlabs','voice01',{})
    p=client.get(f'/api/projects/{pid}').json()
    assert p['status']=='ready',p
    assert p['output_file']=='export.mp4'
    assert p['dub_file']=='dub.wav'
    assert len(produced)==1 and len(preflights)==1
    assert 'Đây là lời thoại tiếng Việt' in produced[0][0]
    assert p['segments'][0]['text']=='Đây là phụ đề tiếng Việt không bị xóa.'
    assert 'nghe lại' in p['message']
    report=client.get(f'/api/projects/{pid}/voice-timing-report')
    assert report.status_code==200
    out=report.json()
    assert out['all_within_limit'] is True
    assert out['quality_warning_count']==1
    assert out['auto_fitted'] is True
    row=out['segments'][0]
    assert 1.5 < row['speed_factor'] < 1.8
    assert row['timing_ok'] is True and row['quality_warning'] is True
    assert 'khớp' in row['note']
    assert 0.9 < _duration(config.PROJECTS_DIR/pid/'dub.wav') < 1.5
    assert 2.1 < _duration(config.PROJECTS_DIR/pid/'export.mp4') < 2.7
    video=client.get(p['export_url'])
    assert video.status_code==200 and len(video.content)>2000


def test_260_percent_speech_uses_chained_atempo_without_failure(client,monkeypatch):
    pid=_new_project(client)
    produced,_=_mock_tts(monkeypatch,2.6)
    jobs.dubbing(pid,'voice01',provider='elevenlabs')
    data=client.get(f'/api/projects/{pid}/voice-timing-report').json()
    assert data['all_within_limit'] is True
    assert 2.5 < data['max_speed_factor'] < 2.9
    assert data['quality_warning_count']==1
    assert len(produced)==1
    assert client.get(f'/api/projects/{pid}').json()['status']=='ready'


def test_truly_impossible_speech_reports_editable_text_instead_of_truncating(client,monkeypatch):
    pid=_new_project(client)
    _mock_tts(monkeypatch,3.75)
    with pytest.raises(RuntimeError,match='rút gọn riêng ô'):
        jobs.dubbing(pid,'voice01',provider='elevenlabs')
    # Keep captions/source and a concrete report so the user can edit only speech.
    project=client.get(f'/api/projects/{pid}').json()
    assert project['segments'][0]['voice_text'].startswith('Đây là lời thoại')
    assert project['video_url']
    out=client.get(f'/api/projects/{pid}/voice-timing-report').json()
    assert out['all_within_limit'] is False
    assert out['segments'][0]['timing_ok'] is False


def test_render_text_explains_automatic_fitting():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text(encoding='utf-8')
    assert 'Mỗi câu được tự căn vào thời lượng cảnh' in html
    assert 'sẽ báo lỗi khi câu quá dài' not in html
