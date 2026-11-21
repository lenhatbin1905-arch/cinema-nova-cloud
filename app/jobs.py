"""Actual asynchronous media processing, local worker. No fake progress/success."""
import json
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import config, db
from .media import probe, ffmpeg_render
from .subtitles import make_ass, make_srt, verify_segments
from . import engines

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='vietframe-media')
logger = logging.getLogger('vietframe.jobs')


def submit(pid, fn, *args):
    def run():
        try:
            fn(pid, *args)
        except Exception as exc:
            logger.exception('Job failed project=%s', pid)
            db.update(pid,status='error',progress=0,message=str(exc)[:600])
    return executor.submit(run)


def path_for(pid):
    folder = config.PROJECTS_DIR / pid
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def finish_video(pid, source: Path):
    details = probe(source)
    db.update(pid,video_file=source.name,duration=details['duration'],status='ready',progress=100,
              message='Đã sẵn sàng biên tập.')


def import_url(pid, url):
    db.update(pid,status='downloading',progress=5,message='Đang tải video thực tế…')
    if not engines.available('yt_dlp'):
        raise RuntimeError('Thiếu yt-dlp, hãy cài requirements.txt.')
    import yt_dlp
    folder = path_for(pid)

    def hook(d):
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            got = d.get('downloaded_bytes') or 0
            progress = min(86, 5 + int(80 * got / total)) if total else 30
            db.update(pid,progress=progress,message='Đang tải video từ nền tảng…')

    opts = dict(outtmpl=str(folder/'source.%(ext)s'),format='bv*+ba/best',
                merge_output_format='mp4',noplaylist=True,playlistend=1,quiet=True,
                no_warnings=True,max_filesize=config.MAX_UPLOAD_MB*1024*1024,
                progress_hooks=[hook])
    with yt_dlp.YoutubeDL(opts) as yd:
        info = yd.extract_info(url, download=True)
        if not info:
            raise RuntimeError('Không tải được. Video có thể riêng tư hoặc nền tảng yêu cầu đăng nhập.')
    videos = sorted((p for p in folder.glob('source.*') if p.suffix.lower() in {'.mp4','.webm','.mov','.mkv'}),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError('Nền tảng không trả về file video. Hãy thử upload file bạn có quyền sử dụng.')
    candidate = videos[0]
    if candidate.stat().st_size > config.MAX_UPLOAD_MB * 1024 * 1024:
        candidate.unlink(missing_ok=True)
        raise RuntimeError('Video vượt quá giới hạn dung lượng.')
    finish_video(pid,candidate)


def transcription(pid):
    data = db.get(pid)
    if not data or not data['video_file']:
        raise ValueError('Chưa có video nguồn.')
    db.update(pid,status='transcribing',progress=15,message='Whisper đang phân tích lời thoại…')
    source = path_for(pid)/data['video_file']
    segments = engines.transcribe(source)
    db.update(pid,segments_json=json.dumps(segments,ensure_ascii=False),output_file=None,dub_file=None,status='ready',progress=100,
              message=f'Đã nhận dạng {len(segments)} câu. Kiểm tra trước khi xuất.')


def translation(pid, source_language, target_language):
    data=db.get(pid)
    if not data or not data['segments']:
        raise ValueError('Chưa có câu phụ đề để dịch.')
    db.update(pid,status='translating',progress=12,message='Đang dịch bằng mô hình offline…')
    result=engines.translate_segments(data['segments'],source_language,target_language)
    db.update(pid,segments_json=json.dumps(result,ensure_ascii=False),output_file=None,dub_file=None,status='ready',progress=100,
              message='Đã dịch. Hãy kiểm tra từ ngữ và font trước khi xuất.')


def render(pid, style):
    data=db.get(pid)
    if not data or not data['video_file']:
        raise ValueError('Thiếu video nguồn.')
    if not data['segments']:
        raise ValueError('Cần nhập ít nhất một câu phụ đề.')
    segments=verify_segments(data['segments'],data['duration'])
    folder=path_for(pid)
    source=folder/data['video_file']
    ass=folder/'subtitles.ass'
    metadata = probe(source)
    video_stream = next(s for s in metadata['streams'] if s.get('codec_type') == 'video')
    resolution = (int(video_stream['width']), int(video_stream['height']))
    ass.write_text(make_ass(segments,style,resolution=resolution),encoding='utf-8-sig')
    (folder/'subtitles.srt').write_text(make_srt(segments),encoding='utf-8-sig')
    output=folder/'export.mp4'
    db.update(pid,status='rendering',progress=10,message='FFmpeg đang xuất MP4, vui lòng giữ ứng dụng chạy…')
    dubbed = (folder/data['dub_file']) if data.get('dub_file') else None
    ffmpeg_render(source,ass,output,audio=dubbed)
    probe(output)
    db.update(pid,output_file=output.name,status='ready',progress=100,
              message='Xuất MP4 hoàn tất, có thể xem hoặc tải về.')


def ai_video(pid,prompt):
    folder=path_for(pid)
    db.update(pid,status='generating',progress=10,message='Model đang tạo video bằng GPU cục bộ…')
    output=folder/'source.mp4'
    engines.generate_video_local(prompt,output)
    finish_video(pid,output)


def dubbing(pid, voice):
    project=db.get(pid)
    if not project or not project['video_file'] or not project['segments']:
        raise ValueError('Cần có video và phụ đề đã dịch trước khi lồng tiếng.')
    if not engines.kokoro_is_ready():
        raise RuntimeError('KokoroTTS không phản hồi. Hãy bật máy chủ giọng nói miễn phí cục bộ.')
    segments=verify_segments(project['segments'],project['duration'])
    if len(segments)>80:
        raise RuntimeError('Lồng tiếng bản đầu tối đa 80 câu mỗi video.')
    folder=path_for(pid)
    prepared=[]
    db.update(pid,status='dubbing',progress=5,message='Đang tạo giọng Việt thật bằng KokoroTTS…')
    for index,seg in enumerate(segments):
        raw=folder/f'voice-{index:03}.wav'
        processed=folder/f'voice-align-{index:03}.wav'
        engines.kokoro_synthesize(seg['text'],voice,raw)
        # Each utterance is placed on its own fixed timeline; fail on extreme speed-up
        # instead of cropping the end of a sentence silently.
        from subprocess import run
        duration_result=run(['ffprobe','-v','error','-show_entries','format=duration',
                             '-of','default=nk=1:nw=1',str(raw)],capture_output=True,text=True,timeout=25)
        if duration_result.returncode:
            raise RuntimeError('KokoroTTS trả âm thanh không đọc được.')
        sound_duration=float(duration_result.stdout.strip())
        slot=seg['end']-seg['start']
        rate=max(1.0,sound_duration/slot)
        if rate>1.35:
            raise RuntimeError(f'Câu {index+1} dài quá thời gian cho phép ({rate:.2f}x). Hãy rút ngắn câu dịch hoặc tăng thời lượng đoạn.')
        start_ms=round(seg['start']*1000)
        filter=f'atempo={rate:.5f},apad,atrim=duration={slot:.3f},adelay={start_ms}|{start_ms}'
        cmd=['ffmpeg','-nostdin','-hide_banner','-v','error','-y','-i',str(raw),'-af',filter,
             '-ar','24000','-ac','2',str(processed)]
        converted=run(cmd,capture_output=True,text=True,timeout=180)
        if converted.returncode:
            raise RuntimeError('Căn thời gian thoại thất bại: '+converted.stderr[-320:])
        prepared.append(processed)
        db.update(pid,progress=5+int(80*(index+1)/len(segments)),
                  message=f'Đã tạo giọng {index+1}/{len(segments)} câu…')
    if not prepared:
        raise RuntimeError('Không có câu để tạo giọng.')
    combined=folder/'dub.wav'
    command=['ffmpeg','-nostdin','-hide_banner','-v','error','-y']
    for item in prepared:
        command+=['-i',str(item)]
    inputs=''.join(f'[{i}:a]' for i in range(len(prepared)))
    command+=['-filter_complex',f'{inputs}amix=inputs={len(prepared)}:duration=longest:normalize=0[out]',
              '-map','[out]','-ar','24000','-ac','2',str(combined)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=600)
    if result.returncode or not combined.exists():
        raise RuntimeError('Ghép giọng thất bại: '+result.stderr[-300:])
    for file in list(folder.glob('voice-*.wav'))+list(folder.glob('voice-align-*.wav')):
        file.unlink(missing_ok=True)
    db.update(pid,dub_file='dub.wav',output_file=None,status='ready',progress=100,
              message='Đã lồng tiếng cục bộ. Xuất MP4 để ghép giọng với hình.')
