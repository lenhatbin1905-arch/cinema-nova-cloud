import json
import os
import shutil
import subprocess
from pathlib import Path
from .config import MAX_DURATION_SECONDS


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


def ffmpeg_render(source: Path, ass: Path, output: Path, audio: Path | None = None):
    if not installed('ffmpeg'):
        raise RuntimeError('Chưa cài FFmpeg trên máy chủ.')
    # Chdir to the per-project directory, so all filter input names are safe basename literals.
    temporary = output.with_name(output.stem+'.partial'+output.suffix)
    temporary.unlink(missing_ok=True)
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
           '-i', source.name]
    if audio:
        cmd += ['-i', audio.name]
    cmd += ['-vf', f'ass={ass.name}', '-map', '0:v:0']
    if audio:
        cmd += ['-map', '1:a:0', '-c:a', 'aac', '-af', 'apad', '-shortest']
    else:
        cmd += ['-map', '0:a?', '-c:a', 'aac']
    cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt','yuv420p',
            '-movflags','+faststart', temporary.name]
    try:
        result = subprocess.run(cmd, cwd=source.parent, capture_output=True, text=True, timeout=1800)
        if result.returncode or not temporary.is_file():
            raise RuntimeError('Xuất video thất bại: '+result.stderr[-900:])
        probe(temporary)
        os.replace(temporary,output)
        return output
    finally:
        temporary.unlink(missing_ok=True)
