import pytest
from app.subtitles import make_srt,make_ass,verify_segments,sanitize_color

SAMPLES=[{'start':0.3,'end':2.4,'text':'Đừng bỏ cuộc nhé!'},{'start':2.7,'end':4.0,'text':'Hãy tin vào chính mình.'}]

def test_srt_vietnamese():
    srt=make_srt(SAMPLES)
    assert 'Đừng bỏ cuộc nhé!' in srt
    assert '00:00:00,300 --> 00:00:02,400' in srt

def test_ass_vietnamese_unicode():
    s=make_ass(SAMPLES,{'font':'DejaVu Sans','color':'#FFD700','outline_color':'#0F1011'})
    assert 'Đừng bỏ cuộc nhé!' in s
    assert '&H0000D7FF' in s
    assert 'Style: Main,DejaVu Sans' in s

def test_escape_ass_override():
    s=make_ass([{'start':0,'end':1,'text':'{\\pos(0,0)} \n nhé'}],{})
    assert '{\\pos(0,0)}' not in s
    assert '｛' in s

def test_reject_invalid_style_color():
    with pytest.raises(ValueError):sanitize_color('expression(foo)')

def test_reject_bad_time():
    with pytest.raises(ValueError):verify_segments([{'start':3,'end':2,'text':'hi'}],10)
