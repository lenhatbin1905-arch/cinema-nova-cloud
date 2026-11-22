"""Tests for original-subtitle replacement at its erased position and word animation."""
import re
import pytest
from app import cleanup, subtitles


def _events(ass):
    return [line for line in ass.splitlines() if line.startswith('Dialogue:')]


def _text_of(event):
    # Remove ASS format prefix and all producer-authored ASS override tags.
    content = event.split(',,', 1)[1] if ',,' in event else event
    content = content.split(',,')[-1]
    return re.sub(r'\{[^{}]*\}', '', content).strip()


def test_word_pop_copies_all_vietnamese_words_and_timed_position():
    message = 'Có lúc những cơn sóng rất mạnh nhưng người thuyền trưởng vẫn bình tĩnh vượt qua tất cả.'
    segment = {'start': 0.2, 'end': 4.2, 'text': message}
    region = {'x':15, 'y':84, 'w':70, 'h':10,
              'start':0.2, 'end':4.2, 'purpose':'subtitle', 'method':'glyph'}
    script = subtitles.make_ass([segment], {'caption_mode':'word_pop'},
                                resolution=(1080,1920), cleanup_regions=[region])
    events = _events(script)
    assert len(events) > 3
    assert r'\an5\pos(540,1709)' in script
    assert r'\fad(' in script
    assert r'\t(' in script
    assert ' '.join(_text_of(event) for event in events) == message
    assert events[0].startswith('Dialogue: 0,0:00:00.20,')
    assert '0:00:04.20' in events[-1]


def test_original_caption_placement_is_not_used_for_logo_or_legacy_mask():
    cue = {'start':0.0,'end':2.0,'text':'Chào bạn'}
    logo = {'x':75,'y':3,'w':20,'h':8,'purpose':'logo'}
    legacy = {'x':15,'y':84,'w':70,'h':10}
    for region in (logo,legacy):
        ass = subtitles.make_ass([cue], {'caption_mode':'full'},
                                 cleanup_regions=[region])
        assert r'\pos(' not in ass
        assert len(_events(ass))==1


def test_different_subtitle_boxes_follow_correct_cues():
    cues = [{'start':0,'end':1.8,'text':'Câu một'},
            {'start':2.0,'end':3.8,'text':'Câu hai'}]
    regs = [{'x':15,'y':80,'w':70,'h':10,'start':0,'end':1.8,'purpose':'subtitle'},
            {'x':15,'y':85,'w':70,'h':10,'start':2,'end':3.8,'purpose':'subtitle'}]
    events=_events(subtitles.make_ass(cues, {'caption_mode':'full'},
                                     resolution=(1000,1000),cleanup_regions=regs))
    assert r'\pos(500,850)' in events[0]
    assert r'\pos(500,900)' in events[1]


def test_invalid_caption_mode_and_cleanup_purpose_rejected():
    with pytest.raises(ValueError):
        subtitles.make_ass([{'start':0,'end':1,'text':'X'}],
                           {'caption_mode':'untrusted'})
    with pytest.raises(ValueError):
        cleanup.validate_regions([{'x':10,'y':80,'w':50,'h':10,
                                   'method':'glyph','purpose':'invalid'}])


def test_valid_cleanup_replacement_roi_keeps_purpose_and_time():
    regions=cleanup.validate_regions([
      {'x':15,'y':84,'w':70,'h':10,'start':0.2,'end':1.5,
       'method':'glyph','purpose':'subtitle'}])
    assert regions[0]['purpose']=='subtitle'
    assert regions[0]['start']==0.2 and regions[0]['end']==1.5


def test_frontend_references_word_pop_and_real_original_subtitle_region():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text(encoding='utf8')
    js=(root/'static/app.js').read_text(encoding='utf8')
    assert 'id="style-caption-mode"' in html
    assert 'id="cleanup-purpose"' in html
    assert 'subtitleReplacementRegion' in js
    assert 'previewWordPop' in js
    assert 'r.purpose' in js
    assert 'cleanup-use-cue' in js



def test_draw_english_subtitle_area_supports_full_video_and_cleanup_purpose():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text(encoding='utf8')
    js=(root/'static/app.js').read_text(encoding='utf8')
    css=(root/'static/style.css').read_text(encoding='utf8')
    assert 'id="mark-caption-region"' in html
    assert 'id="cleanup-draw-layer"' in html
    assert 'id="cleanup-all-video"' in html
    assert "function finishCaptionDrawing(evt)" in js
    assert "function toggleCaptionDrawing(force)" in js
    assert "drawLayer.addEventListener('pointerdown'" in js
    assert "drawLayer.addEventListener('pointerup'" in js
    assert "['x','y','w','h'].every(k=>Number.isInteger(r[k]))" in js
    assert "Number(state.selected?.duration||$('#player').duration)" in js
    assert "#cleanup-draw-layer.active" in css
    assert "style.caption_mode==='word_pop'" in js


def test_caption_selection_purpose_roundtrip_with_api(client):
    import io
    from tests.test_api import fake_video
    video = fake_video()
    p = client.post('/api/projects/upload',
        data={'license_confirmed':'true'},
        files={'file':('roi.mp4',io.BytesIO(video),'video/mp4')}).json()
    pid = p['id']
    first = client.put(f'/api/projects/{pid}/cleanup',json={'regions':[
        {'x':15,'y':70,'w':50,'h':8,'start':0,'end':2.2,
         'method':'glyph','purpose':'subtitle'}]})
    assert first.status_code==200,first.text
    saved = first.json()['cleanup_regions'][0]
    assert saved['purpose']=='subtitle'
    assert saved['x']==15 and saved['y']==70
    assert saved['start']==0 and saved['end']==2.2
    assert saved['method']=='glyph'
