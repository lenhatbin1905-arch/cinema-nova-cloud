"""Local-first video studio API. A production deployment MUST add auth and rate limits."""
import json
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import config, db, jobs, engines
from .media import probe
from .subtitles import verify_segments, make_srt, make_ass
from .url_guard import classify_url
from .style_match import sample_reference_style


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    db.mark_interrupted_jobs()
    yield


app = FastAPI(title='VietFrame Studio',version='0.3.0',lifespan=lifespan,docs_url='/api/docs')
app.mount('/static',StaticFiles(directory=str(config.PROJECT_ROOT/'static')),name='static')


@app.middleware('http')
async def security_headers(request: Request, call_next):
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
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
    return response



@app.get('/')
def homepage():
    return FileResponse(config.PROJECT_ROOT/'static/index.html')


@app.get('/api/health')
def health():
    return {'status':'ok','version':'0.3.0','mode':'local-first'}


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
    if not engines.kokoro_is_ready():
        raise HTTPException(503,'KokoroTTS chưa chạy trên máy cục bộ.')
    _claim(pid,'dubbing','Đã xếp hàng lồng tiếng Việt.')
    jobs.submit(pid,jobs.dubbing,request.voice)
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
