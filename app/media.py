import json
import os
import shutil
import subprocess
from pathlib import Path
from .config import MAX_DURATION_SECONDS
from .cleanup import filter_chain, validate_regions
from .precision import precision_video, limited_video_dimensions


def installed(binary):
    return shutil.which(binary) is not None


def probe(file_path: Path) -> dict:
    if not installed('ffprobe'):
        raise RuntimeError('Chưa cài FFmpeg/ffprobe trên máy chủ.')
    result = subprocess.run([
        'ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_type,width,height',
        '-of','json',str(file_path)], capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise ValueError('Không đọc được video hợp lệ: ' + result.stderr[:240])
    meta = json.loads(result.stdout)
    if not any(s.get('codec_type') == 'video' for s in meta.get('streams', [])):
        raise ValueError('Tệp không có luồng hình ảnh video.')
    duration = float(meta.get('format', {}).get('duration') or 0)
    if not 0 < duration <= MAX_DURATION_SECONDS:
        raise ValueError(f'Video phải dài từ 1 giây đến {MAX_DURATION_SECONDS} giây.')
    return {'duration': duration, 'streams': meta.get('streams', [])}


def ffmpeg_render(source: Path, ass: Path, output: Path, audio: Path | None = None, regions=None):
    if not installed('ffmpeg'):
        raise RuntimeError('Chưa cài FFmpeg trên máy chủ.')
    # Chdir to the per-project directory, so all filter input names are safe basename literals.
    temporary = output.with_name(output.stem+'.partial'+output.suffix)
    temporary.unlink(missing_ok=True)
    regions=validate_regions(regions or [])
    cleaned=source.parent/'precision_noaudio.mp4'
    cleaned.unlink(missing_ok=True)
    use_glyph=any(r['method']=='glyph' for r in regions)
    if use_glyph:
        precision_video(source,cleaned,regions)
    video_input=cleaned if use_glyph else source
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
           '-filter_threads', '1', '-filter_complex_threads', '1',
           '-threads', '1', '-i', video_input.name]
    if audio:
        cmd += ['-i', audio.name]
    elif use_glyph:
        cmd += ['-i',source.name]
    try:
        meta=probe(source)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError('Không đọc được nguồn video hợp lệ trước khi xuất.') from exc
    # Glyph inpaint may downscale to fit Render Free; calculate filter pixels
    # from the processed video, not the original source resolution.
    actual=probe(video_input) if use_glyph else meta
    video=next(s for s in actual['streams'] if s.get('codec_type') == 'video')
    video_width,video_height=int(video['width']),int(video['height'])
    filters=filter_chain(regions, video_width, video_height)
    # Stay below 512MiB on the free host; use an even-dimension,
    # aspect-preserving 720p/1280px-long-edge export for large sources.
    max_edge=int(os.getenv('VIETFRAME_MAX_VIDEO_EDGE','1280'))
    out_width,out_height=limited_video_dimensions(video_width,video_height,max_edge)
    if (out_width,out_height)!=(video_width,video_height):
        filters.append(f'scale={out_width}:{out_height}:flags=lanczos')
    filters.append(f'ass={ass.name}')
    cmd += ['-vf', ','.join(filters), '-map', '0:v:0']
    if audio:
        cmd += ['-map', '1:a:0', '-c:a', 'aac', '-af', 'apad', '-shortest']
    else:
        cmd += ['-map', '1:a?' if use_glyph else '0:a?', '-c:a', 'aac']
    cmd += ['-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '21', '-pix_fmt','yuv420p',
            '-movflags','+faststart', str(temporary)]
    try:
        result = subprocess.run(cmd, cwd=source.parent, capture_output=True, text=True, timeout=1800)
        if result.returncode or not temporary.is_file():
            raise RuntimeError('Xuất video thất bại: '+result.stderr[-900:])
        probe(temporary)
        os.replace(temporary,output)
        return output
    finally:
        temporary.unlink(missing_ok=True)
        cleaned.unlink(missing_ok=True)
