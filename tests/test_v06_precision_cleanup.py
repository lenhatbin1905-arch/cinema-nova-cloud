"""v0.6 regression: no half-screen blur, no cleanup outside caption times."""
import cv2
import numpy as np
import pytest
from app.cleanup import validate_regions, filter_chain, inpaint_frame
from app.media import ffmpeg_render, probe
from app.subtitles import make_ass

def test_reject_blanket_strips_and_bad_time():
    for bad in (
        {'x':0,'y':68,'w':100,'h':30},
        {'x':5,'y':75,'w':91,'h':12},
        {'x':10,'y':78,'w':80,'h':8,'start':8,'end':7},
        {'x':10,'y':78,'w':80,'h':8,'start':float('nan'),'end':8},
        {'x':10,'y':78,'w':80,'h':8,'method':'paid-ai'},
        {'x':10,'y':78,'w':80,'h':8,'start':1},
    ):
        with pytest.raises(ValueError):validate_regions([bad])

def test_timed_ffmpeg_logo_and_glyph_methods():
    reg={'x':30,'y':78,'w':45,'h':8,'method':'edge','start':1.25,'end':3.5}
    assert filter_chain([reg],576,1024)==["delogo=x=173:y=799:w=259:h=82:show=0:enable='between(t,1.25,3.5)'"]
    assert filter_chain([{**reg,'method':'glyph'}],576,1024)==[]

def base_and_caption():
    h,w=320,240
    baseline=np.full((h,w,3),[64,92,145],dtype=np.uint8)
    baseline[:,:,0]+=np.arange(w,dtype=np.uint8)[None,:]//5
    frame=baseline.copy()
    cv2.putText(frame,'HELLO',(25,255),cv2.FONT_HERSHEY_SIMPLEX,1.0,(10,10,10),5,cv2.LINE_AA)
    cv2.putText(frame,'HELLO',(25,255),cv2.FONT_HERSHEY_SIMPLEX,1.0,(255,255,255),2,cv2.LINE_AA)
    return baseline,frame

def test_precision_mask_only_changes_glyphs_in_time():
    baseline,frame=base_and_caption()
    region={'x':8,'y':71,'w':80,'h':11,'method':'glyph','start':1.5,'end':3.0}
    before=frame.copy()
    untouched,diag=inpaint_frame(before.copy(),[region],1)
    assert np.array_equal(untouched,before) and diag['glyph_pixels']==0
    after,diag=inpaint_frame(before.copy(),[region],2)
    assert diag['glyph_pixels']>30
    assert np.array_equal(after[:200],before[:200])
    assert np.array_equal(after[290:],before[290:])
    roi=np.s_[225:265,15:215]
    mae_before=np.abs(before[roi].astype(float)-baseline[roi]).mean()
    mae_after=np.abs(after[roi].astype(float)-baseline[roi]).mean()
    assert mae_after < mae_before*.75,(mae_before,mae_after)

def test_real_pipeline_precision_preserves_audio(tmp_path):
    from subprocess import run
    h,w=160,240
    raw=tmp_path/'raw.mp4'
    proc=run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i',f'color=c=0x667799:s={w}x{h}:d=1.4:r=12',
              '-f','lavfi','-i','sine=frequency=300:duration=1.4','-vf','drawtext=text=HELLO:fontcolor=white:fontsize=25:x=65:y=124',
              '-c:v','libx264','-c:a','aac','-shortest',str(raw)],capture_output=True,text=True,timeout=40)
    assert proc.returncode==0,proc.stderr
    ass=tmp_path/'subtitles.ass'
    ass.write_text(make_ass([{'start':0.1,'end':1.2,'text':'Xin chào'}],{'font':'DejaVu Sans','font_size':22,'margin_v':22,'outline':2},(w,h)),encoding='utf8')
    output=tmp_path/'final.mp4'
    ffmpeg_render(raw,ass,output,regions=[{'x':10,'y':72,'w':80,'h':11,'start':0,'end':1.25,'method':'glyph'}])
    meta=probe(output)
    assert output.stat().st_size>2000
    assert any(s['codec_type']=='audio' for s in meta['streams'])
    assert any(s['codec_type']=='video' for s in meta['streams'])
    assert not (tmp_path/'precision_noaudio.mp4').exists()

def test_emphasis_yellow_preserves_literal_safe_text():
    ass=make_ass([{'start':0,'end':2,'text':'Tay súng [[nhanh nhất]] {\\untrusted}'}],
                 {'font':'DejaVu Sans','highlight_color':'#FFDE00'},(576,1024))
    assert 'nhanh nhất{\\1c' in ass
    assert '{\\1c&H0000DEFF}' in ass
    assert '{\\untrusted}' not in ass

def test_glyph_cleanup_fails_closed_if_no_caption_pixels(tmp_path):
    from app.precision import precision_video
    from subprocess import run
    original=tmp_path/'blank.mp4'
    result=run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=0x223344:s=240x160:r=12:d=0.4',
                '-c:v','libx264',str(original)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0
    with pytest.raises(RuntimeError,match='Không phát hiện'):
        precision_video(original,tmp_path/'no-text.mp4',[{'x':10,'y':75,'w':70,'h':8,'start':0,'end':1,'method':'glyph'}])
