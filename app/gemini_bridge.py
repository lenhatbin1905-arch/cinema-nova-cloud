"""Gemini video-to-Vietnamese dubbing script adapter.

One owner's encrypted API key. A single video upload + one JSON-only model call.
No billing enrollment, implicit retries, synthetic transcripts, or silent fallback.
Timestamp estimates MUST be reviewed against original audio before publishing.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import base64
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import config, elevenlabs_bridge as eleven, credential_store as store
from .subtitles import verify_segments

API = 'https://generativelanguage.googleapis.com'
MODEL = 'gemini-2.5-flash'
ALLOWED_MODELS = {'gemini-2.5-flash', 'gemini-2.5-flash-lite'}
MAX_ANALYSIS_BYTES = 60 * 1024 * 1024
MAX_ANALYSIS_DURATION = 180.0
MAX_SEGMENTS = 80

PROMPT = '''You are a precise multilingual subtitling and Vietnamese dubbing script editor.
Analyze BOTH the audible speech and the visual cues of the supplied video. The audio is the
primary ground truth for spoken words, NOT a scene summary. Do not invent speech, people,
actions, language, sound effects or motives. If unintelligible, report uncertainty.
Produce one SHORT Vietnamese subtitle and a separate natural, conversational voice_text for
EACH genuinely audible speech turn, with approximate start/end seconds anchored to the AUDIO.
Do not put any subtitles on silent portions. Keep meaning faithful, tone natural for Vietnamese
social video, including names and numbers. Do not add 'like/follow' or advertising.
For overlapping speakers, keep order and mark speaker IDs spk1, spk2 etc consistently.
Voice text should fit the allocated spoken slot naturally at ~3.5 to 4.8 Vietnamese syllables
per second; shorten faithfully rather than accelerating or omitting facts. No stage directions
or voice labels in voice_text. For each item return:
start (number, seconds), end (number, seconds), source_text (literal original-language speech),
text (Vietnamese onscreen subtitle), voice_text (Vietnamese speech for TTS),
speaker (stable spk1/spk2 ID), needs_review (bool).
Return ONLY strict JSON object {"language": "ISO 639-1", "segments": [...], "notes": "..."}.
The original video duration is {duration:.2f} seconds. Every start/end must be within this duration.
If speech is uncertain, use needs_review=true; if you cannot hear speech return an empty array.
'''


def _connect():
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.execute('PRAGMA busy_timeout=30000')
    return con


def init():
    store.init()


def link(api_key: str, *, model: str = MODEL):
    if model not in ALLOWED_MODELS:
        raise ValueError('Chỉ hỗ trợ model Gemini Flash trong danh sách Free-first.')
    key = api_key.strip()
    if not 16 <= len(key) <= 256 or any(ch.isspace() for ch in key):
        raise ValueError('API key Gemini không hợp lệ.')
    try:
        with httpx.Client(base_url=API, trust_env=False, timeout=15, follow_redirects=False) as client:
            res = client.get('/v1beta/models/' + model, headers={'x-goog-api-key': key})
    except httpx.RequestError as exc:
        raise ValueError('Chưa kết nối được API Gemini. Kiểm tra mạng.') from exc
    _check_response(res)
    data = res.json()
    if not isinstance(data, dict) or not data.get('name'):
        raise ValueError('API Gemini chưa trả thông tin model hợp lệ.')
    supported = data.get('supportedGenerationMethods')
    if isinstance(supported, list) and 'generateContent' not in supported:
        raise ValueError('Model Gemini này có thể xem thông tin nhưng không hỗ trợ generateContent. Hãy chọn Flash/Lite khác.')
    store.save('gemini', eleven._fernet().encrypt(key.encode()), model)
    return {'connected': True, 'model': model}


def status():
    row = store.get('gemini')
    return {'connected': bool(row), 'model': row[1] if row else None, 'storage': store.kind(), 'free_first': True,
            'note': 'VietFrame không bật billing. Chỉ dùng API key thuộc dự án Gemini không có billing; API không xác nhận được trạng thái billing.'}


def disconnect():
    store.delete('gemini')
    return {'connected': False}


def _key_model():
    row = store.get('gemini')
    if not row:
        raise ValueError('Chưa liên kết Gemini. Vào Cài đặt để thêm API key Free Tier.')
    try:
        key = eleven._fernet().decrypt(row[0]).decode()
    except Exception as exc:
        raise ValueError('Không giải mã được API key Gemini. Hãy liên kết lại.') from exc
    if row[1] not in ALLOWED_MODELS:
        raise ValueError('Model Gemini không nằm trong danh sách Free-first.')
    return key, row[1]


def _check_response(res):
    if res.status_code in (401, 403):
        raise ValueError('Gemini từ chối API key hoặc model chưa được phép truy cập.')
    if res.status_code == 429:
        raise ValueError('Đã hết hạn mức Gemini hiện tại. Không tự chuyển gói trả phí.')
    if res.status_code >= 400:
        raise ValueError(f'Gemini trả lỗi HTTP {res.status_code}. Hãy kiểm tra model, quota và quyền API.')


def _safe_file_name(name):
    if not re.fullmatch(r'files/[a-zA-Z0-9_-]{8,150}', str(name)):
        raise ValueError('Tên file từ Gemini không hợp lệ.')
    return name


def _upload(client, path: Path, key: str, progress=None):
    size = path.stat().st_size
    if not 1000 < size <= MAX_ANALYSIS_BYTES:
        raise ValueError('Gemini chỉ phân tích video từ 1KB đến 60MB trong bản Free-first.')
    mime = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.mkv': 'video/x-matroska'}.get(path.suffix.lower())
    if not mime:
        raise ValueError('Gemini chưa hỗ trợ định dạng video này.')
    start = client.post('/upload/v1beta/files', headers={
        'x-goog-api-key': key,
        'X-Goog-Upload-Protocol': 'resumable',
        'X-Goog-Upload-Command': 'start',
        'X-Goog-Upload-Header-Content-Length': str(size),
        'X-Goog-Upload-Header-Content-Type': mime},
        json={'file': {'display_name': 'vietframe-video-analysis'}})
    _check_response(start)
    upload_url = start.headers.get('x-goog-upload-url', '')
    parsed = urlsplit(upload_url)
    if parsed.scheme != 'https' or parsed.netloc != 'generativelanguage.googleapis.com':
        raise ValueError('Gemini trả URL upload không thuộc máy chủ Google; đã chặn gửi video.')
    if progress: progress(20, 'Gemini đã cấp phiên nhận video. Đang truyền tệp nguồn…')
    with path.open('rb') as f:
        done = client.post(upload_url, headers={'x-goog-api-key': key, 'X-Goog-Upload-Offset': '0',
            'X-Goog-Upload-Command': 'upload, finalize', 'Content-Length': str(size)}, content=f, timeout=140)
    _check_response(done)
    if progress: progress(46, 'Đã tải video lên Gemini. Chờ Google xử lý âm thanh và hình ảnh…')
    file_info = done.json().get('file', {})
    name = _safe_file_name(file_info.get('name'))
    return name, mime, file_info.get('uri')


def _wait_ready(client, key, name, *, seconds=80, progress=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        r = client.get('/v1beta/' + name, headers={'x-goog-api-key': key}, timeout=20)
        _check_response(r)
        info = r.json()
        state = str(info.get('state') or '').upper()
        if state == 'ACTIVE':
            if progress: progress(67, 'Gemini đã xử lý video. Đang chuẩn bị tạo phụ đề Việt…')
            uri = str(info.get('uri') or '')
            if not uri.startswith('https://'):
                raise ValueError('Gemini chưa trả URI video hợp lệ.')
            return uri
        if state == 'FAILED':
            raise ValueError('Gemini không xử lý được video được tải lên.')
        time.sleep(3)
    raise ValueError('Gemini chưa xử lý xong video trong thời gian cho phép.')


def normalize_script(payload: dict, duration: float):
    if not isinstance(payload, dict) or not isinstance(payload.get('segments'), list):
        raise ValueError('Gemini không trả bản thoại JSON hợp lệ.')
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Thời lượng video không hợp lệ.')
    raw = payload['segments']
    if len(raw) > MAX_SEGMENTS:
        raise ValueError('Gemini tạo quá nhiều câu; cần chia video ngắn hơn.')
    out = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise ValueError(f'Đoạn {i+1} không hợp lệ.')
        try:
            start, end = float(s['start']), float(s['end'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Đoạn {i+1} chưa có mốc thời gian.') from exc
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= duration + 0.1:
            raise ValueError(f'Đoạn {i+1} ngoài thời gian video. Phải kiểm tra lại, không tự đoán.')
        subtitle = str(s.get('text') or '').strip()
        voice = str(s.get('voice_text') or subtitle).strip()
        original = str(s.get('source_text') or '').strip()
        speaker = str(s.get('speaker') or 'spk1').strip()
        if not subtitle or len(subtitle) > 500 or not voice or len(voice) > 500:
            raise ValueError(f'Đoạn {i+1} thiếu nội dung hoặc vượt quá độ dài.')
        if not re.fullmatch(r'spk\d{1,2}', speaker):
            raise ValueError(f'Đoạn {i+1} có ID người nói không hợp lệ.')
        if len(original) > 500:
            raise ValueError('Nguyên văn quá dài.')
        syllables = len(re.findall(r'\S+', voice))
        seconds = end - start
        words_per_second = syllables / seconds
        review = bool(s.get('needs_review', False)) or not original or words_per_second > 4.8
        out.append({'start': start, 'end': end, 'text': subtitle,
            'voice_text': voice, 'source_text': original, 'speaker': speaker,
            'needs_review': review})
    verified = verify_segments(out, duration)
    # Speech durations and overlap are evidence-driven: do not invent padding or change utterance times.
    return {'language': str(payload.get('language') or 'unknown')[:20],
        'segments': verified, 'notes': str(payload.get('notes') or '')[:1500],
        'review_count': sum(bool(s.get('needs_review')) for s in verified)}



MAX_INLINE_VIDEO_BYTES = 12 * 1024 * 1024  # B64 JSON stays below 20MB input limit.


def _prepare_inline_video(source: Path, progress=None):
    """Return a compact playable video; never discard its speech audio.

    Inline avoids 404s caused by resolving an ACTIVE Files API URI at
    generateContent time. Larger inputs are downscaled on the server.
    """
    suffix=source.suffix.lower()
    if source.stat().st_size <= MAX_INLINE_VIDEO_BYTES and suffix in {'.mp4','.webm'}:
        if progress: progress(31,'Video đủ nhỏ. Chuẩn bị phân tích trực tiếp, không dùng tham chiếu Files API…')
        return source, ('video/mp4' if suffix=='.mp4' else 'video/webm'), None
    if progress: progress(20,'Video vượt ngưỡng gửi trực tiếp. Đang nén hình và giữ tiếng nói cho Gemini…')
    temp=tempfile.TemporaryDirectory(prefix='vietframe-gemini-inline-')
    result=Path(temp.name)/'gemini-input.mp4'
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),
         '-map','0:v:0','-map','0:a:0?','-vf','scale=-2:480,fps=12',
         '-c:v','libx264','-preset','veryfast','-crf','31',
         '-maxrate','380k','-bufsize','760k','-c:a','aac','-b:a','48k',
         '-movflags','+faststart','-map_metadata','-1',str(result)]
    try:
        proc=subprocess.run(cmd,capture_output=True,timeout=165,check=False)
        if proc.returncode!=0 or not result.exists():
            raise ValueError('Không nén được video cho Gemini. Hãy thử bản MP4 ngắn hơn.')
        if not 1024 < result.stat().st_size <= MAX_INLINE_VIDEO_BYTES:
            raise ValueError('Video sau khi nén vẫn quá lớn. Hãy cắt video ngắn hơn rồi thử lại.')
    except subprocess.TimeoutExpired as exc:
        temp.cleanup()
        raise ValueError('Nén video quá thời gian trên Render Free. Hãy tải MP4 ngắn hoặc nhẹ hơn.') from exc
    except Exception:
        temp.cleanup()
        raise
    if progress: progress(43,'Đã nén video và giữ âm thanh. Chuẩn bị Gemini viết lời Việt…')
    return result,'video/mp4',temp


def _safe_generation_error(response, model):
    """Return actionable Google error without leaking key, URI or user media."""
    code=response.status_code
    try:
        body=response.json()
        err=body.get('error',{}) if isinstance(body,dict) else {}
        reason=str(err.get('message',''))[:200] if isinstance(err,dict) else ''
    except (ValueError,TypeError,AttributeError):
        reason=''
    # Google error messages can include arbitrary resource strings.
    reason=re.sub(r'https?://\\S+','[đường dẫn]',reason)
    reason=re.sub(r'AIza[A-Za-z0-9_-]+','[ẩn]',reason)
    reason=re.sub(r'files/[A-Za-z0-9_-]+','[tệp]',reason)
    if code==404:
        return ('Gemini không tìm thấy model hoặc tài nguyên ở bước tạo phụ đề '
                '(generateContent, HTTP 404; '+model+'). Video đã được gửi trực tiếp, '
                'không qua Files API. Hãy kiểm tra model có hỗ trợ generateContent trong tài khoản Google AI Studio. '
                + (reason[:130] if reason else ''))
    if code in (401,403):
        return 'Google từ chối quyền Gemini khi tạo phụ đề (HTTP '+str(code)+'). Kiểm tra API key và quyền truy cập model.'
    if code==429:
        return 'Gemini đang hết hạn mức Free hoặc bị giới hạn tần suất. Không chuyển sang gói trả phí.'
    if code >=500:
        return 'Máy chủ Gemini đang gặp lỗi HTTP '+str(code)+'. Hãy thử lại khi dịch vụ ổn định.'
    return 'Gemini không tạo được phụ đề (HTTP '+str(code)+'). '+reason[:145]


def analyze_video(source: Path, duration: float, progress=None):
    """Use inline video data; Files API dereference previously caused HTTP 404."""
    if not 0 < duration <= MAX_ANALYSIS_DURATION:
        raise ValueError('Gemini Free-first hỗ trợ tối đa 180 giây mỗi lượt.')
    if not source.is_file():
        raise ValueError('Video nguồn không tồn tại.')
    if source.stat().st_size > MAX_ANALYSIS_BYTES:
        raise ValueError('Video trên 60MB. Hãy tải bản ngắn hoặc nhẹ hơn.')
    key,model=_key_model()
    temp=None
    if progress: progress(11,'Đang xác minh nguồn video và chuẩn bị gửi Gemini…')
    try:
        path,mime,temp=_prepare_inline_video(source,progress=progress)
        if progress: progress(55,'Đang chuẩn bị video cho Gemini, giữ cả hình và âm thanh…')
        encoded=base64.b64encode(path.read_bytes()).decode('ascii')
        request={
            'contents':[{'role':'user','parts':[
                {'inlineData':{'mimeType':mime,'data':encoded}},
                {'text':PROMPT.replace('{duration:.2f}',f'{duration:.2f}')}] }],
            'generationConfig':{'temperature':0.15,'maxOutputTokens':5500,
                                'responseMimeType':'application/json'}}
        del encoded
        if progress: progress(74,'Gemini đang nhận dạng lời nói và viết phụ đề Việt theo cảnh…')
        try:
            with httpx.Client(base_url=API,trust_env=False,timeout=30,follow_redirects=False) as client:
                response=client.post('/v1beta/models/'+model+':generateContent',
                                     headers={'x-goog-api-key':key},json=request,timeout=140)
        except httpx.RequestError as exc:
            raise ValueError('Kết nối Gemini bị gián đoạn trong khi phân tích video.') from exc
        if response.status_code>=400:
            raise ValueError(_safe_generation_error(response,model))
        if progress: progress(91,'Gemini trả kết quả. Đang kiểm tra phụ đề và mốc thời gian…')
        data=response.json()
        candidates=data.get('candidates') or []
        parts=candidates[0].get('content',{}).get('parts',[]) if candidates else []
        output=''.join(p.get('text','') for p in parts if isinstance(p,dict))
        if not output:
            raise ValueError('Gemini không trả lời thoại có thể dùng. Không tạo phụ đề giả.')
        try:
            script=json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError('Gemini trả bản thoại JSON chưa hợp lệ. Hãy thử clip ngắn hơn.') from exc
        result=normalize_script(script,duration)
        if progress: progress(97,'Đã xác thực lời Việt và thời gian. Đang lưu phụ đề…')
        return result
    finally:
        if temp is not None:
            temp.cleanup()
