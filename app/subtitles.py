"""SRT and ASS subtitle generation with Vietnamese Unicode support."""
import re
from html import escape as html_escape

HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
FONT = re.compile(r'^[\w \-]{1,65}$', re.UNICODE)


def sanitize_color(value: str) -> str:
    if not HEX.fullmatch(value):
        raise ValueError('Màu phải có dạng #RRGGBB.')
    return '&H00' + value[5:7].upper() + value[3:5].upper() + value[1:3].upper()


def verify_segments(segments, max_duration=3600):
    if not isinstance(segments, list) or len(segments) > 500:
        raise ValueError('Tối đa 500 câu phụ đề.')
    valid = []
    for item in segments:
        start = float(item['start'])
        end = float(item['end'])
        text = str(item['text']).strip()
        if not (0 <= start < end <= max_duration + 0.3):
            raise ValueError('Thời gian câu phụ đề không hợp lệ.')
        if not text or len(text) > 500:
            raise ValueError('Mỗi câu phải có từ 1 đến 500 ký tự.')
        valid.append({'start':start,'end':end,'text':text})
    return sorted(valid, key=lambda x: (x['start'],x['end']))


def time_srt(sec: float) -> str:
    milliseconds = round(sec * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, ms = divmod(milliseconds, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def time_ass(sec: float) -> str:
    centiseconds = round(sec * 100)
    hours, centiseconds = divmod(centiseconds, 360000)
    minutes, centiseconds = divmod(centiseconds, 6000)
    seconds, cs = divmod(centiseconds, 100)
    return f'{hours}:{minutes:02}:{seconds:02}.{cs:02}'


def make_srt(segments: list) -> str:
    return '\n'.join(f'{i}\n{time_srt(s["start"])} --> {time_srt(s["end"])}\n{s["text"]}\n' for i,s in enumerate(segments, 1))


def make_ass(segments: list, style: dict, resolution=(1080,1920)) -> str:
    font = style.get('font', 'DejaVu Sans')
    if not FONT.fullmatch(font):
        raise ValueError('Tên font không hợp lệ.')
    color = sanitize_color(style.get('color', '#FFFFFF'))
    outline_color = sanitize_color(style.get('outline_color','#121212'))
    fontsize = int(style.get('font_size', 68))
    outline = int(style.get('outline', 4))
    margin_v = int(style.get('margin_v', 155))
    bold = int(bool(style.get('bold', True))) * -1
    if not (20 <= fontsize <= 160 and 0 <= outline <= 12 and 10 <= margin_v <= 900):
        raise ValueError('Thông số font nằm ngoài giới hạn hỗ trợ.')
    x, y = resolution
    header = f'''[Script Info]
Title: VietFrame Studio Subtitles
ScriptType: v4.00+
PlayResX: {x}
PlayResY: {y}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{fontsize},{color},&H000000FF,{outline_color},&H7F000000,{bold},0,0,0,100,100,0,0,1,{outline},1,2,35,35,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    rows = []
    for s in segments:
        # Escape ASS override syntax, so foreign subtitles cannot inject styling commands.
        safe = s['text'].replace('\\', '＼').replace('{','｛').replace('}','｝')
        safe = safe.replace('\r',' ').replace('\n','\\N')
        rows.append(f'Dialogue: 0,{time_ass(s["start"])},{time_ass(s["end"])},Main,,0,0,0,,{safe}')
    return header + '\n'.join(rows) + '\n'
