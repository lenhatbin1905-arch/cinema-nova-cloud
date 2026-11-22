"""Free-first video studio with single-owner sessions and protected media API."""
import json
import hmac
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import config, db, jobs, engines, auth, elevenlabs_bridge as eleven, cleanup
from .media import probe
from .subtitles import verify_segments, make_srt, make_ass
from .url_guard import classify_url
from .style_match import sample_reference_style


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    auth.init()
    eleven.init()
    db.mark_interrupted_jobs()
    yield


app = FastAPI(title='VietFrame Studio',version='0.5.0',lifespan=lifespan,docs_url='/api/docs')
app.mount('/static',StaticFiles(directory=str(config.PROJECT_ROOT/'static')),name='static')


@app.middleware('http')
async def security_and_auth(request: Request, call_next):
    path = request.url.path
    method = request.method.upper()
    public = {'/login', '/api/health', '/api/auth/config', '/api/auth/setup', '/api/auth/login'}
    protected = not (path in public or (path.startswith('/static/') and path != '/static/index.html'))
    session = auth.get_session(request.cookies.get(auth.COOKIE_NAME)) if protected else None
    request.state.auth_session = session
    if protected and session is None:
        response = RedirectResponse('/login', status_code=303) if path == '/' or path == '/static/index.html' else JSONResponse({'detail': 'Vui lòng đăng nhập để tiếp tục.'}, status_code=401)
    elif protected and method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not _same_origin(request):
        response = JSONResponse({'detail': 'Yêu cầu không cùng nguồn.'}, status_code=403)
    elif protected and method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
        response = JSONResponse({'detail': 'Mã xác nhận phiên không hợp lệ. Tải lại trang rồi thử lại.'}, status_code=403)
    else:
        response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers['Cache-Control'] = 'no-store' if path.startswith('/api/') or path in {'/', '/login'} else 'no-cache'
    return response


def _same_origin(request: Request):
    # CSRF header is also required. Reject cross-site Origin/Referer when provided.
    origin = request.headers.get('origin')
    referer = request.headers.get('referer')
    host = request.headers.get('host', '')
    if origin:
        from urllib.parse import urlsplit
        return urlsplit(origin).netloc == host
    if referer:
        from urllib.parse import urlsplit
        return urlsplit(referer).netloc == host
    return True


def _setup_authorized(request: Request, provided: str):
    secret = config.SETUP_TOKEN
    if secret:
        return hmac.compare_digest(provided, secret)
    return (request.client.host if request.client else '') in {'127.0.0.1', '::1', 'localhost'}


class OwnerCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class OwnerSetup(OwnerCredentials):
    setup_token: str = Field(default='', max_length=256)


class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12, max_length=128)


def _cookie_secure(request: Request):
    return config.COOKIE_SECURE or request.url.scheme == 'https'


def _start_login(response: JSONResponse, request: Request, user):
    token, csrf = auth.new_session(user['id'])
    response = JSONResponse({'email': user['email'], 'csrf': csrf, 'authenticated': True}, status_code=response.status_code)
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True,
                        secure=_cookie_secure(request), samesite='strict',
                        max_age=auth.SESSION_TTL, path='/')
    return response


@app.get('/')
def homepage():
    return FileResponse(config.PROJECT_ROOT/'static/index.html')


@app.get('/login')
def login_page(request: Request):
    if auth.get_session(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse('/', status_code=303)
    return FileResponse(config.PROJECT_ROOT/'static/login.html')


@app.get('/api/auth/config')
def auth_config(request: Request):
    return {'setup_required': not auth.has_owner(),
            'local_setup_allowed': not config.SETUP_TOKEN and _setup_authorized(request, ''),
            'setup_token_required': bool(config.SETUP_TOKEN)}


@app.post('/api/auth/setup', status_code=201)
def setup(request: Request, credentials: OwnerSetup):
    if not _same_origin(request):
        raise HTTPException(403, 'Yêu cầu không cùng nguồn.')
    if not _setup_authorized(request, credentials.setup_token):
        raise HTTPException(403, 'Thiết lập chủ sở hữu chỉ được thực hiện cục bộ hoặc bằng mã thiết lập máy chủ.')
    if auth.has_owner():
        raise HTTPException(409, 'Tài khoản đã tồn tại. Hãy đăng nhập.')
    try:
        user = auth.create_first_owner(credentials.email, credentials.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _start_login(JSONResponse({}, status_code=201), request, user)


@app.post('/api/auth/login')
def login(request: Request, credentials: OwnerCredentials):
    if not _same_origin(request):
        raise HTTPException(403, 'Yêu cầu không cùng nguồn.')
    ip = request.client.host if request.client else 'unknown'
    try:
        user = auth.validate_login(credentials.email, credentials.password, ip)
    except PermissionError as exc:
        raise HTTPException(429, str(exc)) from exc
    if not user:
        raise HTTPException(401, 'Email hoặc mật khẩu không đúng.')
    return _start_login(JSONResponse({}), request, user)


@app.get('/api/auth/me')
def my_account(request: Request):
    row = request.state.auth_session
    return {'authenticated': True, 'email': row['email'], 'csrf': row['csrf']}


@app.post('/api/auth/logout')
def logout(request: Request):
    auth.revoke_session(request.cookies.get(auth.COOKIE_NAME, ''))
    response = JSONResponse({'ok': True})
    response.delete_cookie(auth.COOKIE_NAME, path='/', samesite='strict', httponly=True, secure=_cookie_secure(request))
    return response


@app.post('/api/auth/change-password')
def update_password(request: Request, body: ChangePassword):
    try:
        result = auth.change_password(request.state.auth_session['id'], body.old_password, body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not result:
        raise HTTPException(422, 'Mật khẩu hiện tại không đúng.')
    response = JSONResponse({'ok': True, 'login_required': True})
    response.delete_cookie(auth.COOKIE_NAME, path='/', samesite='strict', httponly=True, secure=_cookie_secure(request))
    return response


@app.get('/api/health')
def health():
    return {'status':'ok','version':'0.5.0','mode':'local-first'}


@app.get('/api/capabilities')
def get_capabilities():
    return engines.capabilities()


@app.get('/api/projects')
def list_projects():
    return [_shape(p) for p in db.all_projects()]


@app.get('/api/projects/{pid}')
def get_project(pid: str):
    return _shape(_find(pid))


class LinkRequest(BaseModel):
    url: str = Field(min_length=10,max_length=2048)
    license_confirmed: bool


@app.post('/api/projects/from-url',status_code=202)
def from_url(req: LinkRequest):
    if not req.license_confirmed:
        raise HTTPException(422,'Bạn phải xác nhận có quyền sử dụng video này.')
    try:
        platform=classify_url(req.url)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    pid=uuid4().hex
    db.create(pid,'Video từ '+platform,source=platform,source_url=req.url,status='queued')
    jobs.submit(pid,jobs.import_url,req.url)
    return _shape(_find(pid))


@app.post('/api/projects/upload',status_code=201)
async def upload_video(file: UploadFile = File(...), title: str = Form('Video của tôi'),
                       license_confirmed: bool = Form(False)):
    if not license_confirmed:
        raise HTTPException(422,'Cần xác nhận bạn có quyền sử dụng video.')
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in {'.mp4','.mov','.webm','.mkv'}:
        raise HTTPException(422,'Chỉ nhận MP4, MOV, WEBM hoặc MKV.')
    pid=uuid4().hex
    directory=jobs.path_for(pid)
    destination=directory/('source'+suffix)
    size=0
    try:
        with destination.open('wb') as dst:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > config.MAX_UPLOAD_MB*1024*1024:
                    raise HTTPException(413,'Tệp vượt giới hạn dung lượng.')
                dst.write(chunk)
        details=probe(destination)
        db.create(pid,(title or file.filename or 'Video của tôi').strip()[:140],source='upload',status='ready')
        jobs.finish_video(pid,destination)
        return _shape(_find(pid))
    except Exception as exc:
        shutil.rmtree(directory,ignore_errors=True)
        if isinstance(exc,HTTPException):
            raise
        raise HTTPException(422,str(exc)) from exc
    finally:
        await file.close()


class Segment(BaseModel):
    start: float
    end: float
    text: str = Field(min_length=1,max_length=500)


class SegmentRequest(BaseModel):
    segments: list[Segment] = Field(max_length=500)


@app.put('/api/projects/{pid}/segments')
def save_segments(pid: str,req: SegmentRequest):
    p=_find(pid)
    _ensure_editable(p)
    try:
        cleaned=verify_segments([x.model_dump() for x in req.segments],p['duration'])
    except (ValueError,TypeError,KeyError) as exc:
        raise HTTPException(422,str(exc)) from exc
    accepted, changed = db.save_segments_if_ready(pid, cleaned)
    if not accepted:
        raise HTTPException(409,'Dự án đang xử lý. Thử lại sau khi tác vụ hoàn thành.')
    if changed:
        folder = config.PROJECTS_DIR / pid
        (folder / 'dub.wav').unlink(missing_ok=True)
        (folder / 'export.mp4').unlink(missing_ok=True)
    return _shape(_find(pid))


@app.post('/api/projects/{pid}/transcribe',status_code=202)
def transcribe(pid: str):
    p=_find(pid)
    _ensure_editable(p)
    if not engines.capabilities()['offline_transcription']:
        raise HTTPException(503,'Whisper offline chưa được cài. Xem hướng dẫn cài AI miễn phí.')
    _claim(pid,'transcribing','Đã xếp hàng nhận diện lời thoại.')
    jobs.submit(pid,jobs.transcription)
    return {'accepted':True,'project_id':pid}


class TranslateRequest(BaseModel):
    source_language: str = Field(pattern=r'^[a-z]{2,3}$',default='en')
    target_language: str = Field(pattern=r'^[a-z]{2,3}$',default='vi')


@app.post('/api/projects/{pid}/translate',status_code=202)
def translate(pid: str,req: TranslateRequest):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Chưa có phụ đề để dịch.')
    if not engines.capabilities()['offline_translation']:
        raise HTTPException(503,'Argos Translate offline chưa được cài.')
    _claim(pid,'translating','Đã xếp hàng dịch phụ đề.')
    jobs.submit(pid,jobs.translation,req.source_language,req.target_language)
    return {'accepted':True,'project_id':pid}


class CleanupRect(BaseModel):
    start: float | None = Field(default=None,ge=0,le=1800)
    end: float | None = Field(default=None,ge=0,le=1800)
    method: str = Field(default='glyph',pattern='^(glyph|edge) int = Field(ge=0, le=98)
    y: int = Field(ge=0, le=98)
    w: int = Field(ge=2, le=100)
    h: int = Field(ge=2, le=100)


class CleanupRequest(BaseModel):
    regions: list[CleanupRect] = Field(max_length=80)


@app.put('/api/projects/{pid}/cleanup')
def set_cleanup(pid: str, payload: CleanupRequest):
    p = _find(pid)
    _ensure_editable(p)
    try:
        normalized = cleanup.validate_regions([x.model_dump() for x in payload.regions])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not db.save_cleanup_if_ready(pid, normalized):
        raise HTTPException(409, 'Dự án đang xử lý.')
    return _shape(_find(pid))


class SubtitleStyle(BaseModel):
    font: str = 'DejaVu Sans'
    font_size: int = Field(default=32,ge=20,le=160)
    highlight_color: str = Field(default='#FFD42A',pattern=r'^#[0-9A-Fa-f]{6}
    color: str = Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline_color: str = Field(default='#121212',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline: int = Field(default=4,ge=0,le=12)
    margin_v: int = Field(default=155,ge=10,le=900)
    bold: bool = True


@app.post('/api/projects/{pid}/render',status_code=202)
def render(pid: str,style: SubtitleStyle):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần nhập ít nhất một câu phụ đề.')
    if not engines.capabilities()['ffmpeg']:
        raise HTTPException(503,'Chưa có FFmpeg/ffprobe.')
    _claim(pid,'rendering','Đã xếp hàng xuất MP4.')
    jobs.submit(pid,jobs.render,style.model_dump())
    return {'accepted':True,'project_id':pid}


class DubRequest(BaseModel):
    voice: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_\-]+$')
    provider: str = Field(default='kokoro', pattern=r'^(kokoro|elevenlabs)$')


@app.get('/api/integrations/elevenlabs')
def eleven_status():
    return eleven.is_connected()


class ElevenLinkRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=256)


@app.post('/api/integrations/elevenlabs/link')
def eleven_link(body: ElevenLinkRequest):
    try:
        return eleven.link(body.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete('/api/integrations/elevenlabs')
def eleven_disconnect():
    return eleven.disconnect()


@app.get('/api/integrations/elevenlabs/voices')
def eleven_voices():
    try:
        return {'voices': eleven.voices()}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/voices')
def list_voices():
    if not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa được bật cục bộ.')
    try:
        return engines.kokoro_voices()
    except Exception as exc:
        raise HTTPException(502,'Không lấy được giọng từ KokoroTTS: '+str(exc)[:100]) from exc


@app.post('/api/projects/{pid}/dub',status_code=202)
def dub_video(pid: str,request: DubRequest):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần có phụ đề đã dịch trước khi lồng tiếng.')
    if request.provider == 'kokoro' and not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa chạy trên máy cục bộ.')
    if request.provider == 'elevenlabs':
        if not eleven.is_connected()['connected']:
            raise HTTPException(503,'Chưa liên kết ElevenLabs ở Cài đặt.')
        try:
            eleven.free_quota_available(sum(len(s['text']) for s in p['segments']))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    _claim(pid,'dubbing','Đã xếp hàng lồng tiếng Việt.')
    jobs.submit(pid,jobs.dubbing,request.voice,request.provider)
    return {'accepted':True,'project_id':pid}


@app.get('/api/projects/{pid}/reference-style')
def get_reference_style(pid: str):
    p=_find(pid)
    if not p.get('video_file'):
        raise HTTPException(409,'Chưa có video nguồn.')
    return sample_reference_style(jobs.path_for(pid)/p['video_file'])


class GenerateRequest(BaseModel):
    prompt: str=Field(min_length=12,max_length=1300)


@app.post('/api/ai/create-video',status_code=202)
def ai_create_video(req: GenerateRequest):
    if not engines.capabilities()['ai_video_local']:
        raise HTTPException(503,'AI tạo video chưa khả dụng: cần GPU và model local. Không phát sinh phí API.')
    pid=uuid4().hex
    db.create(pid,'Video AI: '+req.prompt[:70],source='ai-video',status='queued')
    jobs.submit(pid,jobs.ai_video,req.prompt)
    return _shape(_find(pid))


@app.get('/api/projects/{pid}/file/{kind}')
def media_file(pid: str,kind: str):
    p=_find(pid)
    available={'source':p['video_file'],'export':p['output_file'],'dub':p.get('dub_file')}
    if kind not in available:
        raise HTTPException(404,'Loại tệp không hợp lệ.')
    name=available[kind]
    if not name or Path(name).name!=name:
        raise HTTPException(404,'Không có tệp này.')
    file=jobs.path_for(pid)/name
    if not file.is_file():
        raise HTTPException(404,'Tệp chưa được tạo.')
    return FileResponse(file,media_type=('audio/wav' if file.suffix=='.wav' else 'video/mp4' if file.suffix=='.mp4' else None),
                        filename='vietframe-'+kind+file.suffix if kind=='export' else None)


@app.get('/api/projects/{pid}/subtitles.srt')
def download_srt(pid: str):
    p=_find(pid)
    text=make_srt(verify_segments(p['segments'],max(p['duration'],1)))
    return PlainTextResponse(text,media_type='text/plain; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="vietframe.srt"'})


def _find(pid):
    if not re.fullmatch(r'[0-9a-f]{32}',pid):
        raise HTTPException(404,'Không có dự án này.')
    p=db.get(pid)
    if p is None:
        raise HTTPException(404,'Không tìm thấy dự án.')
    return p


def _claim(pid, status, message):
    if not db.claim_ready_project(pid,status,message):
        raise HTTPException(409,'Dự án đang xử lý. Chỉ có thể chạy một tác vụ tại một thời điểm.')


@app.post('/api/projects/{pid}/recover')
def recover(pid: str):
    p=_find(pid)
    if p['status'] != 'error' or not p.get('video_file'):
        raise HTTPException(409,'Chỉ khôi phục được dự án lỗi có video nguồn.')
    source=config.PROJECTS_DIR / pid / p['video_file']
    if not source.is_file():
        raise HTTPException(409,'Video nguồn không còn tồn tại. Hãy nhập lại từ đầu.')
    if not db.recover_project(pid):
        raise HTTPException(409,'Dự án đã thay đổi trạng thái; hãy tải lại.')
    return _shape(_find(pid))


def _ensure_editable(p):
    if p['status']!='ready':
        raise HTTPException(409,'Dự án đang xử lý hoặc gặp lỗi; hãy kiểm tra trạng thái trước.')


def _shape(p):
    return {**p,'video_url':f'/api/projects/{p["id"]}/file/source' if p['video_file'] else None,
            'export_url':f'/api/projects/{p["id"]}/file/export?updated={p["updated_at"]}' if p['output_file'] else None,
            'dub_url':f'/api/projects/{p["id"]}/file/dub' if p.get('dub_file') else None}
)
    x: int = Field(ge=0, le=98)
    y: int = Field(ge=0, le=98)
    w: int = Field(ge=2, le=100)
    h: int = Field(ge=2, le=100)


class CleanupRequest(BaseModel):
    regions: list[CleanupRect] = Field(max_length=3)


@app.put('/api/projects/{pid}/cleanup')
def set_cleanup(pid: str, payload: CleanupRequest):
    p = _find(pid)
    _ensure_editable(p)
    try:
        normalized = cleanup.validate_regions([x.model_dump() for x in payload.regions])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not db.save_cleanup_if_ready(pid, normalized):
        raise HTTPException(409, 'Dự án đang xử lý.')
    return _shape(_find(pid))


class SubtitleStyle(BaseModel):
    font: str = 'DejaVu Sans'
    font_size: int = Field(default=68,ge=20,le=160)
    color: str = Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline_color: str = Field(default='#121212',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline: int = Field(default=4,ge=0,le=12)
    margin_v: int = Field(default=155,ge=10,le=900)
    bold: bool = True


@app.post('/api/projects/{pid}/render',status_code=202)
def render(pid: str,style: SubtitleStyle):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần nhập ít nhất một câu phụ đề.')
    if not engines.capabilities()['ffmpeg']:
        raise HTTPException(503,'Chưa có FFmpeg/ffprobe.')
    _claim(pid,'rendering','Đã xếp hàng xuất MP4.')
    jobs.submit(pid,jobs.render,style.model_dump())
    return {'accepted':True,'project_id':pid}


class DubRequest(BaseModel):
    voice: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_\-]+$')
    provider: str = Field(default='kokoro', pattern=r'^(kokoro|elevenlabs)$')


@app.get('/api/integrations/elevenlabs')
def eleven_status():
    return eleven.is_connected()


class ElevenLinkRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=256)


@app.post('/api/integrations/elevenlabs/link')
def eleven_link(body: ElevenLinkRequest):
    try:
        return eleven.link(body.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete('/api/integrations/elevenlabs')
def eleven_disconnect():
    return eleven.disconnect()


@app.get('/api/integrations/elevenlabs/voices')
def eleven_voices():
    try:
        return {'voices': eleven.voices()}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/voices')
def list_voices():
    if not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa được bật cục bộ.')
    try:
        return engines.kokoro_voices()
    except Exception as exc:
        raise HTTPException(502,'Không lấy được giọng từ KokoroTTS: '+str(exc)[:100]) from exc


@app.post('/api/projects/{pid}/dub',status_code=202)
def dub_video(pid: str,request: DubRequest):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần có phụ đề đã dịch trước khi lồng tiếng.')
    if request.provider == 'kokoro' and not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa chạy trên máy cục bộ.')
    if request.provider == 'elevenlabs':
        if not eleven.is_connected()['connected']:
            raise HTTPException(503,'Chưa liên kết ElevenLabs ở Cài đặt.')
        try:
            eleven.free_quota_available(sum(len(s['text']) for s in p['segments']))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    _claim(pid,'dubbing','Đã xếp hàng lồng tiếng Việt.')
    jobs.submit(pid,jobs.dubbing,request.voice,request.provider)
    return {'accepted':True,'project_id':pid}


@app.get('/api/projects/{pid}/reference-style')
def get_reference_style(pid: str):
    p=_find(pid)
    if not p.get('video_file'):
        raise HTTPException(409,'Chưa có video nguồn.')
    return sample_reference_style(jobs.path_for(pid)/p['video_file'])


class GenerateRequest(BaseModel):
    prompt: str=Field(min_length=12,max_length=1300)


@app.post('/api/ai/create-video',status_code=202)
def ai_create_video(req: GenerateRequest):
    if not engines.capabilities()['ai_video_local']:
        raise HTTPException(503,'AI tạo video chưa khả dụng: cần GPU và model local. Không phát sinh phí API.')
    pid=uuid4().hex
    db.create(pid,'Video AI: '+req.prompt[:70],source='ai-video',status='queued')
    jobs.submit(pid,jobs.ai_video,req.prompt)
    return _shape(_find(pid))


@app.get('/api/projects/{pid}/file/{kind}')
def media_file(pid: str,kind: str):
    p=_find(pid)
    available={'source':p['video_file'],'export':p['output_file'],'dub':p.get('dub_file')}
    if kind not in available:
        raise HTTPException(404,'Loại tệp không hợp lệ.')
    name=available[kind]
    if not name or Path(name).name!=name:
        raise HTTPException(404,'Không có tệp này.')
    file=jobs.path_for(pid)/name
    if not file.is_file():
        raise HTTPException(404,'Tệp chưa được tạo.')
    return FileResponse(file,media_type=('audio/wav' if file.suffix=='.wav' else 'video/mp4' if file.suffix=='.mp4' else None),
                        filename='vietframe-'+kind+file.suffix if kind=='export' else None)


@app.get('/api/projects/{pid}/subtitles.srt')
def download_srt(pid: str):
    p=_find(pid)
    text=make_srt(verify_segments(p['segments'],max(p['duration'],1)))
    return PlainTextResponse(text,media_type='text/plain; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="vietframe.srt"'})


def _find(pid):
    if not re.fullmatch(r'[0-9a-f]{32}',pid):
        raise HTTPException(404,'Không có dự án này.')
    p=db.get(pid)
    if p is None:
        raise HTTPException(404,'Không tìm thấy dự án.')
    return p


def _claim(pid, status, message):
    if not db.claim_ready_project(pid,status,message):
        raise HTTPException(409,'Dự án đang xử lý. Chỉ có thể chạy một tác vụ tại một thời điểm.')


@app.post('/api/projects/{pid}/recover')
def recover(pid: str):
    p=_find(pid)
    if p['status'] != 'error' or not p.get('video_file'):
        raise HTTPException(409,'Chỉ khôi phục được dự án lỗi có video nguồn.')
    source=config.PROJECTS_DIR / pid / p['video_file']
    if not source.is_file():
        raise HTTPException(409,'Video nguồn không còn tồn tại. Hãy nhập lại từ đầu.')
    if not db.recover_project(pid):
        raise HTTPException(409,'Dự án đã thay đổi trạng thái; hãy tải lại.')
    return _shape(_find(pid))


def _ensure_editable(p):
    if p['status']!='ready':
        raise HTTPException(409,'Dự án đang xử lý hoặc gặp lỗi; hãy kiểm tra trạng thái trước.')


def _shape(p):
    return {**p,'video_url':f'/api/projects/{p["id"]}/file/source' if p['video_file'] else None,
            'export_url':f'/api/projects/{p["id"]}/file/export?updated={p["updated_at"]}' if p['output_file'] else None,
            'dub_url':f'/api/projects/{p["id"]}/file/dub' if p.get('dub_file') else None}
)
    color: str = Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline_color: str = Field(default='#121212',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline: int = Field(default=4,ge=0,le=12)
    margin_v: int = Field(default=155,ge=10,le=900)
    bold: bool = True


@app.post('/api/projects/{pid}/render',status_code=202)
def render(pid: str,style: SubtitleStyle):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần nhập ít nhất một câu phụ đề.')
    if not engines.capabilities()['ffmpeg']:
        raise HTTPException(503,'Chưa có FFmpeg/ffprobe.')
    _claim(pid,'rendering','Đã xếp hàng xuất MP4.')
    jobs.submit(pid,jobs.render,style.model_dump())
    return {'accepted':True,'project_id':pid}


class DubRequest(BaseModel):
    voice: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_\-]+$')
    provider: str = Field(default='kokoro', pattern=r'^(kokoro|elevenlabs)$')


@app.get('/api/integrations/elevenlabs')
def eleven_status():
    return eleven.is_connected()


class ElevenLinkRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=256)


@app.post('/api/integrations/elevenlabs/link')
def eleven_link(body: ElevenLinkRequest):
    try:
        return eleven.link(body.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete('/api/integrations/elevenlabs')
def eleven_disconnect():
    return eleven.disconnect()


@app.get('/api/integrations/elevenlabs/voices')
def eleven_voices():
    try:
        return {'voices': eleven.voices()}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/voices')
def list_voices():
    if not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa được bật cục bộ.')
    try:
        return engines.kokoro_voices()
    except Exception as exc:
        raise HTTPException(502,'Không lấy được giọng từ KokoroTTS: '+str(exc)[:100]) from exc


@app.post('/api/projects/{pid}/dub',status_code=202)
def dub_video(pid: str,request: DubRequest):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần có phụ đề đã dịch trước khi lồng tiếng.')
    if request.provider == 'kokoro' and not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa chạy trên máy cục bộ.')
    if request.provider == 'elevenlabs':
        if not eleven.is_connected()['connected']:
            raise HTTPException(503,'Chưa liên kết ElevenLabs ở Cài đặt.')
        try:
            eleven.free_quota_available(sum(len(s['text']) for s in p['segments']))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    _claim(pid,'dubbing','Đã xếp hàng lồng tiếng Việt.')
    jobs.submit(pid,jobs.dubbing,request.voice,request.provider)
    return {'accepted':True,'project_id':pid}


@app.get('/api/projects/{pid}/reference-style')
def get_reference_style(pid: str):
    p=_find(pid)
    if not p.get('video_file'):
        raise HTTPException(409,'Chưa có video nguồn.')
    return sample_reference_style(jobs.path_for(pid)/p['video_file'])


class GenerateRequest(BaseModel):
    prompt: str=Field(min_length=12,max_length=1300)


@app.post('/api/ai/create-video',status_code=202)
def ai_create_video(req: GenerateRequest):
    if not engines.capabilities()['ai_video_local']:
        raise HTTPException(503,'AI tạo video chưa khả dụng: cần GPU và model local. Không phát sinh phí API.')
    pid=uuid4().hex
    db.create(pid,'Video AI: '+req.prompt[:70],source='ai-video',status='queued')
    jobs.submit(pid,jobs.ai_video,req.prompt)
    return _shape(_find(pid))


@app.get('/api/projects/{pid}/file/{kind}')
def media_file(pid: str,kind: str):
    p=_find(pid)
    available={'source':p['video_file'],'export':p['output_file'],'dub':p.get('dub_file')}
    if kind not in available:
        raise HTTPException(404,'Loại tệp không hợp lệ.')
    name=available[kind]
    if not name or Path(name).name!=name:
        raise HTTPException(404,'Không có tệp này.')
    file=jobs.path_for(pid)/name
    if not file.is_file():
        raise HTTPException(404,'Tệp chưa được tạo.')
    return FileResponse(file,media_type=('audio/wav' if file.suffix=='.wav' else 'video/mp4' if file.suffix=='.mp4' else None),
                        filename='vietframe-'+kind+file.suffix if kind=='export' else None)


@app.get('/api/projects/{pid}/subtitles.srt')
def download_srt(pid: str):
    p=_find(pid)
    text=make_srt(verify_segments(p['segments'],max(p['duration'],1)))
    return PlainTextResponse(text,media_type='text/plain; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="vietframe.srt"'})


def _find(pid):
    if not re.fullmatch(r'[0-9a-f]{32}',pid):
        raise HTTPException(404,'Không có dự án này.')
    p=db.get(pid)
    if p is None:
        raise HTTPException(404,'Không tìm thấy dự án.')
    return p


def _claim(pid, status, message):
    if not db.claim_ready_project(pid,status,message):
        raise HTTPException(409,'Dự án đang xử lý. Chỉ có thể chạy một tác vụ tại một thời điểm.')


@app.post('/api/projects/{pid}/recover')
def recover(pid: str):
    p=_find(pid)
    if p['status'] != 'error' or not p.get('video_file'):
        raise HTTPException(409,'Chỉ khôi phục được dự án lỗi có video nguồn.')
    source=config.PROJECTS_DIR / pid / p['video_file']
    if not source.is_file():
        raise HTTPException(409,'Video nguồn không còn tồn tại. Hãy nhập lại từ đầu.')
    if not db.recover_project(pid):
        raise HTTPException(409,'Dự án đã thay đổi trạng thái; hãy tải lại.')
    return _shape(_find(pid))


def _ensure_editable(p):
    if p['status']!='ready':
        raise HTTPException(409,'Dự án đang xử lý hoặc gặp lỗi; hãy kiểm tra trạng thái trước.')


def _shape(p):
    return {**p,'video_url':f'/api/projects/{p["id"]}/file/source' if p['video_file'] else None,
            'export_url':f'/api/projects/{p["id"]}/file/export?updated={p["updated_at"]}' if p['output_file'] else None,
            'dub_url':f'/api/projects/{p["id"]}/file/dub' if p.get('dub_file') else None}
)
    x: int = Field(ge=0, le=98)
    y: int = Field(ge=0, le=98)
    w: int = Field(ge=2, le=100)
    h: int = Field(ge=2, le=100)


class CleanupRequest(BaseModel):
    regions: list[CleanupRect] = Field(max_length=3)


@app.put('/api/projects/{pid}/cleanup')
def set_cleanup(pid: str, payload: CleanupRequest):
    p = _find(pid)
    _ensure_editable(p)
    try:
        normalized = cleanup.validate_regions([x.model_dump() for x in payload.regions])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not db.save_cleanup_if_ready(pid, normalized):
        raise HTTPException(409, 'Dự án đang xử lý.')
    return _shape(_find(pid))


class SubtitleStyle(BaseModel):
    font: str = 'DejaVu Sans'
    font_size: int = Field(default=68,ge=20,le=160)
    color: str = Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline_color: str = Field(default='#121212',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline: int = Field(default=4,ge=0,le=12)
    margin_v: int = Field(default=155,ge=10,le=900)
    bold: bool = True


@app.post('/api/projects/{pid}/render',status_code=202)
def render(pid: str,style: SubtitleStyle):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần nhập ít nhất một câu phụ đề.')
    if not engines.capabilities()['ffmpeg']:
        raise HTTPException(503,'Chưa có FFmpeg/ffprobe.')
    _claim(pid,'rendering','Đã xếp hàng xuất MP4.')
    jobs.submit(pid,jobs.render,style.model_dump())
    return {'accepted':True,'project_id':pid}


class DubRequest(BaseModel):
    voice: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_\-]+$')
    provider: str = Field(default='kokoro', pattern=r'^(kokoro|elevenlabs)$')


@app.get('/api/integrations/elevenlabs')
def eleven_status():
    return eleven.is_connected()


class ElevenLinkRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=256)


@app.post('/api/integrations/elevenlabs/link')
def eleven_link(body: ElevenLinkRequest):
    try:
        return eleven.link(body.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete('/api/integrations/elevenlabs')
def eleven_disconnect():
    return eleven.disconnect()


@app.get('/api/integrations/elevenlabs/voices')
def eleven_voices():
    try:
        return {'voices': eleven.voices()}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/voices')
def list_voices():
    if not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa được bật cục bộ.')
    try:
        return engines.kokoro_voices()
    except Exception as exc:
        raise HTTPException(502,'Không lấy được giọng từ KokoroTTS: '+str(exc)[:100]) from exc


@app.post('/api/projects/{pid}/dub',status_code=202)
def dub_video(pid: str,request: DubRequest):
    p=_find(pid)
    _ensure_editable(p)
    if not p['segments']:
        raise HTTPException(422,'Cần có phụ đề đã dịch trước khi lồng tiếng.')
    if request.provider == 'kokoro' and not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa chạy trên máy cục bộ.')
    if request.provider == 'elevenlabs':
        if not eleven.is_connected()['connected']:
            raise HTTPException(503,'Chưa liên kết ElevenLabs ở Cài đặt.')
        try:
            eleven.free_quota_available(sum(len(s['text']) for s in p['segments']))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    _claim(pid,'dubbing','Đã xếp hàng lồng tiếng Việt.')
    jobs.submit(pid,jobs.dubbing,request.voice,request.provider)
    return {'accepted':True,'project_id':pid}


@app.get('/api/projects/{pid}/reference-style')
def get_reference_style(pid: str):
    p=_find(pid)
    if not p.get('video_file'):
        raise HTTPException(409,'Chưa có video nguồn.')
    return sample_reference_style(jobs.path_for(pid)/p['video_file'])


class GenerateRequest(BaseModel):
    prompt: str=Field(min_length=12,max_length=1300)


@app.post('/api/ai/create-video',status_code=202)
def ai_create_video(req: GenerateRequest):
    if not engines.capabilities()['ai_video_local']:
        raise HTTPException(503,'AI tạo video chưa khả dụng: cần GPU và model local. Không phát sinh phí API.')
    pid=uuid4().hex
    db.create(pid,'Video AI: '+req.prompt[:70],source='ai-video',status='queued')
    jobs.submit(pid,jobs.ai_video,req.prompt)
    return _shape(_find(pid))


@app.get('/api/projects/{pid}/file/{kind}')
def media_file(pid: str,kind: str):
    p=_find(pid)
    available={'source':p['video_file'],'export':p['output_file'],'dub':p.get('dub_file')}
    if kind not in available:
        raise HTTPException(404,'Loại tệp không hợp lệ.')
    name=available[kind]
    if not name or Path(name).name!=name:
        raise HTTPException(404,'Không có tệp này.')
    file=jobs.path_for(pid)/name
    if not file.is_file():
        raise HTTPException(404,'Tệp chưa được tạo.')
    return FileResponse(file,media_type=('audio/wav' if file.suffix=='.wav' else 'video/mp4' if file.suffix=='.mp4' else None),
                        filename='vietframe-'+kind+file.suffix if kind=='export' else None)


@app.get('/api/projects/{pid}/subtitles.srt')
def download_srt(pid: str):
    p=_find(pid)
    text=make_srt(verify_segments(p['segments'],max(p['duration'],1)))
    return PlainTextResponse(text,media_type='text/plain; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="vietframe.srt"'})


def _find(pid):
    if not re.fullmatch(r'[0-9a-f]{32}',pid):
        raise HTTPException(404,'Không có dự án này.')
    p=db.get(pid)
    if p is None:
        raise HTTPException(404,'Không tìm thấy dự án.')
    return p


def _claim(pid, status, message):
    if not db.claim_ready_project(pid,status,message):
        raise HTTPException(409,'Dự án đang xử lý. Chỉ có thể chạy một tác vụ tại một thời điểm.')


@app.post('/api/projects/{pid}/recover')
def recover(pid: str):
    p=_find(pid)
    if p['status'] != 'error' or not p.get('video_file'):
        raise HTTPException(409,'Chỉ khôi phục được dự án lỗi có video nguồn.')
    source=config.PROJECTS_DIR / pid / p['video_file']
    if not source.is_file():
        raise HTTPException(409,'Video nguồn không còn tồn tại. Hãy nhập lại từ đầu.')
    if not db.recover_project(pid):
        raise HTTPException(409,'Dự án đã thay đổi trạng thái; hãy tải lại.')
    return _shape(_find(pid))


def _ensure_editable(p):
    if p['status']!='ready':
        raise HTTPException(409,'Dự án đang xử lý hoặc gặp lỗi; hãy kiểm tra trạng thái trước.')


def _shape(p):
    return {**p,'video_url':f'/api/projects/{p["id"]}/file/source' if p['video_file'] else None,
            'export_url':f'/api/projects/{p["id"]}/file/export?updated={p["updated_at"]}' if p['output_file'] else None,
            'dub_url':f'/api/projects/{p["id"]}/file/dub' if p.get('dub_file') else None}
