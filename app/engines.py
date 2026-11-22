"""Optional CPU/GPU engines: never report synthetic jobs as completed."""
import importlib.util
import os
import shutil
import httpx
from urllib.parse import urlsplit
from . import config


def available(module):
    return importlib.util.find_spec(module) is not None


def capabilities():
    gpu = False
    if available('torch'):
        import torch
        gpu = torch.cuda.is_available()
    return {
        'ffmpeg': bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),
        'link_import': available('yt_dlp'),
        'platforms': ['Facebook','YouTube','TikTok','Douyin','Bilibili','Instagram'],
        'offline_transcription': available('faster_whisper'),
        'offline_translation': available('argostranslate'),
        'tts_kokoro_local': kokoro_is_ready(),
        'elevenlabs_link_supported': True,
        'static_text_cleanup': True,
        'ai_video_local': bool(config.ENABLE_LOCAL_VIDEO_GEN and gpu and available('diffusers')),
        'gpu': gpu,
        'note': 'Không có API trả phí. Tính năng chỉ chạy khi đã cài engine/model thật.'
    }


def transcribe(source_path):
    if not available('faster_whisper'):
        raise RuntimeError('Cần cài requirements-ai.txt để sử dụng Whisper miễn phí trên máy.')
    from faster_whisper import WhisperModel
    # CPU-first, users with GPU can override config in future release.
    model = WhisperModel(config.WHISPER_MODEL, device='cpu', compute_type='int8')
    results, info = model.transcribe(str(source_path), beam_size=5, vad_filter=True)
    return [{'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()}
            for s in results if s.text.strip()]


def translate_segments(segments, source_language, target_language='vi'):
    if not available('argostranslate'):
        raise RuntimeError('Chưa cài Argos Translate. Hãy cài requirements-ai.txt và gói ngôn ngữ phù hợp.')
    from argostranslate import translate
    installed = translate.get_installed_languages()
    source = next((x for x in installed if x.code == source_language), None)
    target = next((x for x in installed if x.code == target_language), None)
    if not source or not target:
        raise RuntimeError('Thiếu gói dịch offline '+source_language+' → '+target_language+'.')
    translator = source.get_translation(target)
    if not translator:
        raise RuntimeError('Chưa có cặp dịch offline tương thích; không tạo bản dịch giả.')
    return [{**seg, 'text': translator.translate(seg['text'])} for seg in segments]


def generate_video_local(prompt: str, output_path):
    if not capabilities()['ai_video_local']:
        raise RuntimeError('AI tạo video miễn phí cần máy có GPU, diffusers và model. Chưa cấu hình.')
    import torch
    from diffusers import CogVideoXPipeline
    from diffusers.utils import export_to_video
    pipe = CogVideoXPipeline.from_pretrained(config.VIDEO_MODEL_ID, torch_dtype=torch.float16)
    pipe.enable_model_cpu_offload()
    frames = pipe(prompt=prompt, num_videos_per_prompt=1, num_inference_steps=40, num_frames=49,
                  guidance_scale=6).frames[0]
    export_to_video(frames, str(output_path), fps=8)
    return output_path


def _kokoro_url():
    url = config.KOKORO_TTS_URL
    if not url:
        raise RuntimeError('Hãy bật KokoroTTS cục bộ và cấu hình KOKORO_TTS_URL.')
    parsed=urlsplit(url)
    if parsed.scheme != 'http' or (parsed.hostname not in {'127.0.0.1','localhost','kokoro'}):
        raise RuntimeError('Chỉ cho phép KokoroTTS trên local hoặc Docker nội bộ (kokoro).')
    return url


def _tts_headers():
    return {'Authorization':'Bearer '+config.KOKORO_TTS_API_KEY} if config.KOKORO_TTS_API_KEY else {}


def kokoro_is_ready():
    if not config.KOKORO_TTS_URL:
        return False
    try:
        with httpx.Client(timeout=1.4, trust_env=False) as cli:
            return cli.get(_kokoro_url()+'/health/ready').status_code == 200
    except Exception:
        return False


def kokoro_voices():
    url=_kokoro_url()
    with httpx.Client(timeout=8,trust_env=False) as cli:
        r=cli.get(url+'/tts/voices',headers=_tts_headers())
        r.raise_for_status()
        return r.json()


def kokoro_synthesize(text, voice, filename):
    if not text or len(text)>500:
        raise ValueError('Văn bản giọng nói tối đa 500 ký tự/câu.')
    if not (1 <= len(voice) <= 80 and all(x.isalnum() or x in {'_','-'} for x in voice)):
        raise ValueError('Mã giọng không hợp lệ.')
    with httpx.Client(timeout=120,trust_env=False,follow_redirects=False) as cli:
        with cli.stream('POST', _kokoro_url()+'/v1/audio/speech',
                        json={'model':'kokoro','input':text,'voice':voice,'response_format':'wav'},
                        headers=_tts_headers()) as response:
            response.raise_for_status()
            with open(filename,'wb') as fp:
                size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>20*1024*1024:
                        raise RuntimeError('KokoroTTS trả file âm thanh quá lớn.')
                    fp.write(chunk)
    if os.stat(filename).st_size < 200:
        raise RuntimeError('KokoroTTS không trả âm thanh hợp lệ.')
    return filename
