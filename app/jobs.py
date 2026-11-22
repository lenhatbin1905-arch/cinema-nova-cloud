"""Actual asynchronous media processing, local worker. No fake progress/success."""
import json
import hashlib
import logging
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import config, db
from .media import probe, ffmpeg_render
from .subtitles import make_ass, make_srt, verify_segments
from . import engines, elevenlabs_bridge as eleven, gemini_bridge as gemini

executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vietframe-media')
logger = logging.getLogger('vietframe.jobs')

# Voice length varies by model, speaker and punctuation. A hard limit of 1.35x
# prematurely failed otherwise valid video projects *after spending TTS quota*.
# FFmpeg atempo preserves pitch and can safely time-fit the observed 1.60x case.
QUALITY_WARNING_TEMPO = 1.35
MAX_AUTO_TEMPO = 3.0  # Beyond this, a human rewrite is more intelligible.


def tempo_filter(rate):
    """Pitch-preserving FFmpeg filter; factors <=2 avoid atempo sample skipping.

    Do not silently crop any speech. High ratios are flagged in the report.
    """
    if not math.isfinite(rate) or rate < 1.0:
        raise ValueError('Tốc độ căn tiếng không hợp lệ.')
    count=max(1,math.ceil(math.log2(rate)))
    factor=rate ** (1.0/count)
    return ','.join(f'atempo={factor:.6f}' for _ in range(count))



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
    if (shutil.which('node')):
        opts['js_runtimes'] = {'node': {}}
    try:
        with yt_dlp.YoutubeDL(opts) as yd:
            info = yd.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        reason = str(exc).casefold()
        if 'failed to extract any player response' in reason:
            raise RuntimeError('YouTube không cung cấp luồng phát cho máy chủ Render. Hãy thử video công khai khác hoặc tải trực tiếp tệp video bạn có quyền sử dụng. Không cần thay API Gemini/ElevenLabs.') from exc
        raise RuntimeError('Không thể tải video từ nền tảng này. Nếu nội dung yêu cầu tài khoản, vùng địa lý hay quyền riêng tư, hãy tải lên tệp video bạn có quyền sử dụng.') from exc
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


def gemini_script(pid):
    data=db.get(pid)
    if not data or not data['video_file']:
        raise RuntimeError('Thiếu video nguồn cần Gemini phân tích.')
    source=path_for(pid)/data['video_file']
    db.update(pid,status='analyzing',progress=10,message='Gemini đang nghe lời gốc và đối chiếu hình ảnh…')
    report=gemini.analyze_video(source, data['duration'], progress=lambda pct,msg: db.update(
        pid,progress=pct,message=msg))
    if not report['segments']:
        raise RuntimeError('Không phát hiện lời nói rõ trong video; không tự tạo phụ đề giả.')
    (path_for(pid)/'gemini-script-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    db.update(pid,segments_json=json.dumps(report['segments'],ensure_ascii=False),
        dub_file=None,output_file=None,status='ready',progress=100,
        message=f'Gemini đề xuất {len(report["segments"])} câu, {report["review_count"]} câu cần soát. Hãy kiểm tra trước khi dùng ElevenLabs.')


def render(pid, style, *, use_dub=True, one_click=False):
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
    db.update(pid,status='rendering',progress=92 if one_click else 10,message='FFmpeg đang ghép chữ, hình và âm thanh thành MP4…')
    dubbed = (folder/data['dub_file']) if use_dub and data.get('dub_file') else None
    ffmpeg_render(source,ass,output,audio=dubbed,regions=data.get('cleanup_regions', []))
    probe(output)
    db.update(pid,output_file=output.name,status='ready',progress=100,
              message='Xuất MP4 hoàn tất, có thể xem hoặc tải về.')


def ai_video(pid,prompt):
    folder=path_for(pid)
    db.update(pid,status='generating',progress=10,message='Model đang tạo video bằng GPU cục bộ…')
    output=folder/'source.mp4'
    engines.generate_video_local(prompt,output)
    finish_video(pid,output)


def dubbing(pid, voice, provider='kokoro', *, one_click=False, voice_map=None):
    project=db.get(pid)
    if not project or not project['video_file'] or not project['segments']:
        raise ValueError('Cần có video và phụ đề đã dịch trước khi lồng tiếng.')
    if provider == 'kokoro' and not engines.kokoro_is_ready():
        raise RuntimeError('KokoroTTS không phản hồi. Hãy bật máy chủ giọng nói miễn phí cục bộ.')
    if provider not in {'kokoro', 'elevenlabs'}:
        raise RuntimeError('Nhà cung cấp giọng không hợp lệ.')
    segments=verify_segments(project['segments'],project['duration'])
    if len(segments)>80:
        raise RuntimeError('Lồng tiếng bản đầu tối đa 80 câu mỗi video.')
    voice_map=voice_map or {}
    if provider == 'elevenlabs':
        eleven.preflight_free_voices(
            [voice]+list(voice_map.values()),
            sum(len(s.get('voice_text') or s['text']) for s in segments)
        )
    folder=path_for(pid)
    prepared=[]
    timing_report=[]
    db.update(pid,status='dubbing',progress=5,message='Đang tạo giọng Việt bằng '+provider+'…')
    for index,seg in enumerate(segments):
        processed=folder/f'voice-align-{index:03}.wav'
        speak=seg.get('voice_text') or seg['text']
        chosen_voice=voice_map.get(seg.get('speaker','spk1'),voice)
        # Stable cache across failed retries, but never reuse audio from another
        # provider, voice, or script revision. Avoid repeated paid TTS calls.
        cache_key=hashlib.sha256(json.dumps([provider,chosen_voice,speak],ensure_ascii=False).encode('utf-8')).hexdigest()[:24]
        ext='mp3' if provider == 'elevenlabs' else 'wav'
        raw=folder/f'voice-cache-{cache_key}.{ext}'
        if not raw.is_file() or raw.stat().st_size == 0:
            raw.unlink(missing_ok=True)
            if provider == 'elevenlabs':
                eleven.synthesize(speak, chosen_voice, raw)
            else:
                engines.kokoro_synthesize(speak,chosen_voice,raw)
        # Measure the actual TTS waveform rather than guessing duration from
        # text length. Keep every spoken word; time-stretch with pitch preservation.
        from subprocess import run
        duration_result=run(['ffprobe','-v','error','-show_entries','format=duration',
                             '-of','default=nk=1:nw=1',str(raw)],capture_output=True,text=True,timeout=25)
        if duration_result.returncode:
            raise RuntimeError('Giọng TTS trả âm thanh không đọc được.')
        try:
            sound_duration=float(duration_result.stdout.strip())
        except ValueError as exc:
            raise RuntimeError('Không đo được thời lượng tiếng nói ElevenLabs.') from exc
        if not math.isfinite(sound_duration) or sound_duration<=0:
            raise RuntimeError('Thời lượng âm thanh TTS không hợp lệ.')
        slot=seg['end']-seg['start']
        rate=max(1.0,sound_duration/slot)
        quality_warning=rate>QUALITY_WARNING_TEMPO
        within_limit=rate<=MAX_AUTO_TEMPO
        timing_report.append({'index':index+1,'speaker':seg.get('speaker','spk1'),
            'start':seg['start'],'end':seg['end'],'voice_id':chosen_voice,
            'slot_seconds':round(slot,3),'raw_audio_seconds':round(sound_duration,3),
            'speed_factor':round(rate,3),'speech_text':speak,
            'timing_ok':within_limit,'quality_warning':quality_warning,
            'note':('Đã tự tăng tốc để khớp thời lượng cảnh, giữ đủ lời thoại; hãy nghe lại độ tự nhiên.'
                    if quality_warning and within_limit else
                    'Câu quá dài, cần rút gọn lời thoại hoặc nới thời gian.'
                    if not within_limit else '')})
        if not within_limit:
            (folder/'voice-timing-report.json').write_text(
                json.dumps(timing_report,ensure_ascii=False,indent=2),encoding='utf-8')
            raise RuntimeError(
                f'Câu {index+1} cần tăng tốc {rate:.2f}x, vượt ngưỡng chất lượng '
                f'{MAX_AUTO_TEMPO:.1f}x. Hãy rút gọn riêng ô "Thoại cho ElevenLabs" '
                'hoặc nới thời gian đoạn; phụ đề đã lưu và video gốc vẫn còn.')
        start_ms=round(seg['start']*1000)
        filters=tempo_filter(rate)
        filter=f'{filters},apad,atrim=duration={slot:.3f},adelay={start_ms}|{start_ms}'
        cmd=['ffmpeg','-nostdin','-hide_banner','-v','error','-y','-i',str(raw),'-af',filter,
             '-ar','24000','-ac','2',str(processed)]
        converted=run(cmd,capture_output=True,text=True,timeout=180)
        if converted.returncode:
            raise RuntimeError('Căn thời gian thoại thất bại: '+converted.stderr[-320:])
        prepared.append(processed)
        db.update(pid,progress=5+int(80*(index+1)/len(segments)),
                  message=(f'Đã căn giọng {index+1}/{len(segments)} câu'
                           + (f' · tăng tốc {rate:.2f}x, cần nghe lại' if quality_warning else '')
                           + '…'))
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
    (folder/'voice-timing-report.json').write_text(json.dumps(timing_report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Keep verified TTS audio cached so retrying export never spends credits
    # synthesizing the same sentence again. Remove only generated alignment files.
    for file in folder.glob('voice-align-*.wav'):
        file.unlink(missing_ok=True)
    warnings=sum(bool(c['quality_warning']) for c in timing_report)
    info=f' · {warnings} câu đã tăng tốc để khớp hình, cần nghe lại' if warnings else ''
    db.update(pid,dub_file='dub.wav',output_file=None,status='rendering' if one_click else 'ready',progress=90 if one_click else 100,
              message=('Đã căn giọng theo câu, đang xuất MP4'+info+'…'
                       if one_click else 'Đã lồng tiếng xong'+info+'. Có thể xuất MP4.'))


def complete_video(pid, style, voice_provider='original', voice=None, voice_map=None):
    """One queued project job: optional timed TTS -> precise cleanup -> caption render -> MP4.

    No synthetic success, silent voice fallback, or extra paid API calls.
    """
    if voice_provider == 'original':
        render(pid, style, use_dub=False, one_click=True)
        return
    if voice_provider not in {'kokoro','elevenlabs'} or not voice:
        raise ValueError('Chưa chọn giọng hợp lệ để lồng tiếng.')
    dubbing(pid, voice, voice_provider, one_click=True, voice_map=voice_map)
    render(pid, style, use_dub=True, one_click=True)
    # Preserve honest quality warnings after the final video render updates status.
    report_path=path_for(pid)/'voice-timing-report.json'
    if report_path.is_file():
        report=json.loads(report_path.read_text(encoding='utf-8'))
        warned=sum(bool(c.get('quality_warning')) for c in report)
        if warned:
            db.update(pid,message=f'Đã xuất MP4. {warned} câu được tự tăng tốc để khớp hình; hãy nghe lại trước khi đăng.')
