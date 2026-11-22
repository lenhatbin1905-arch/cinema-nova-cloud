"""One-owner ElevenLabs connection. Secrets never leave this server after linking."""
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote
import httpx
from cryptography.fernet import Fernet, InvalidToken
from . import config, credential_store as store

API_BASE = 'https://api.elevenlabs.io'
MAX_AUDIO_BYTES = 15 * 1024 * 1024


def _fernet():
    """Encryption key stored on owner's persistent local volume; use env on hosted setups."""
    explicit = os.environ.get('VIETFRAME_CREDENTIAL_ENCRYPTION_KEY', '').strip()
    if explicit:
        return Fernet(explicit.encode())
    path = config.DATA_DIR / '.credential-encryption-key'
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as out:
                out.write(Fernet.generate_key())
    if os.name != 'nt' and path.exists():
        os.chmod(path, 0o600)
    return Fernet(path.read_bytes().strip())


def init():
    store.init()


def _get_key():
    row = store.get('elevenlabs')
    if not row:
        return None
    try:
        return _fernet().decrypt(row[0]).decode('utf-8')
    except InvalidToken as exc:
        raise RuntimeError('Mã hóa khóa ElevenLabs không hợp lệ. Hãy liên kết lại tài khoản.') from exc


def is_connected():
    row = store.get('elevenlabs')
    result={'connected': bool(row), 'label': row[1] if row else None, 'storage': store.kind()}
    if row and 'quyền giới hạn' in row[1]:
        result['limited']=True
        result['warning']='Chỉ chọn được giọng. Cần User → Read để xác minh hạn mức Free trước khi tạo tiếng.'
    return result


def _request(method, path, key, **kwargs):
    try:
        with httpx.Client(base_url=API_BASE, timeout=16, trust_env=False, follow_redirects=False) as client:
            response = client.request(method, path, headers={'xi-api-key': key, 'Accept': 'application/json'}, **kwargs)
        if response.status_code in (401, 403):
            try:
                body = response.json()
                detail = body.get('detail', body) if isinstance(body, dict) else {}
                reason = str(detail.get('message', '')) if isinstance(detail, dict) else ''
            except (ValueError, TypeError, AttributeError):
                reason = ''
            permissions = {
                'user_read': 'User → Read',
                'voices_read': 'Voices → Read',
                'text_to_speech': 'Text to Speech → Access',
            }
            missing = [label for scope, label in permissions.items() if scope in reason.lower()]
            if missing:
                raise ValueError('API key ElevenLabs thiếu quyền: ' + ', '.join(missing) +
                                 '. Mở ElevenLabs → API Keys → Edit key, bật quyền này rồi liên kết lại.')
            raise ValueError('ElevenLabs từ chối API key (401/403). Kiểm tra key, giới hạn IP và các quyền User Read, Voices Read, Text to Speech.')
        if response.status_code == 429:
            raise ValueError('ElevenLabs đã giới hạn lượt sử dụng hoặc hết hạn mức miễn phí.')
        if response.status_code >= 400:
            raise ValueError(f'ElevenLabs trả lỗi HTTP {response.status_code}. Kiểm tra quyền gói tài khoản.')
        return response
    except httpx.RequestError as exc:
        raise ValueError('Không kết nối được máy chủ ElevenLabs; hãy kiểm tra mạng.') from exc


def link(api_key):
    api_key = api_key.strip()
    if not 16 <= len(api_key) <= 256 or any(ch.isspace() for ch in api_key):
        raise ValueError('API key ElevenLabs không hợp lệ.')
    limited = False
    try:
        profile = _request('GET', '/v1/user', api_key).json()
        label = str(profile.get('email') or profile.get('first_name') or 'ElevenLabs')[:120]
    except ValueError as exc:
        # A scoped API key may validly read voices but not user details. Verify an
        # actual required capability before retaining it; invalid keys still fail.
        try:
            voices_data = _request('GET','/v2/voices',api_key,params={'page_size':1}).json()
        except ValueError:
            raise exc
        if not isinstance(voices_data,dict) or not isinstance(voices_data.get('voices'),list):
            raise ValueError('ElevenLabs chưa xác minh được quyền Voices → Read.') from exc
        label = 'ElevenLabs (quyền giới hạn)'
        limited = True
    encrypted = _fernet().encrypt(api_key.encode('utf-8'))
    store.save('elevenlabs', encrypted, label)
    result={'connected': True, 'label': label}
    if limited:
        result['limited']=True
        result['warning']='Đã liên kết để chọn giọng. Cần bật thêm User → Read để xác minh hạn mức Free trước khi tạo tiếng; VietFrame sẽ chặn tạo tiếng cho đến khi có quyền.'
    return result


def disconnect():
    store.delete('elevenlabs')
    return {'connected': False}


def _require_key():
    key = _get_key()
    if not key:
        raise ValueError('Chưa liên kết tài khoản ElevenLabs. Vào Cài đặt để kết nối.')
    return key


def voices():
    key = _require_key()
    data = _request('GET', '/v2/voices', key, params={'page_size': 100}).json()
    result = data.get('voices', [])
    return [{'id': str(v['voice_id']), 'name': str(v.get('name') or v['voice_id'])}
            for v in result if isinstance(v, dict) and v.get('voice_id')]


def free_quota_available(characters):
    """Fail closed: use only free-tier credits; never silently spend paid account money."""
    if not 1 <= characters <= 10000:
        raise ValueError('Văn bản phải có từ 1 đến 10.000 ký tự.')
    key = _require_key()
    subscription = _request('GET', '/v1/user/subscription', key).json()
    tier = str(subscription.get('tier') or '').lower()
    if tier != 'free':
        raise ValueError('Chế độ Free-First chỉ cho phép gói ElevenLabs Free. Đã chặn để tránh phát sinh phí.')
    limit, used = subscription.get('character_limit'), subscription.get('character_count')
    if not isinstance(limit, int) or not isinstance(used, int):
        raise ValueError('Không xác minh được số ký tự còn lại trên gói Free; tạm dừng để tránh phí.')
    remaining = max(0, limit-used)
    if remaining < characters:
        raise ValueError(f'Gói Free còn {remaining} ký tự, không đủ cho yêu cầu {characters} ký tự.')
    return {'remaining': remaining, 'required': characters, 'tier': tier}


def synthesize(text, voice_id, filename):
    if not 1 <= len(text) <= 500:
        raise ValueError('Mỗi câu ElevenLabs tối đa 500 ký tự trong VietFrame.')
    if not 1 <= len(voice_id) <= 80 or not all(c.isalnum() or c in '-_' for c in voice_id):
        raise ValueError('Mã giọng ElevenLabs không hợp lệ.')
    free_quota_available(len(text))
    key = _require_key()
    path = f'/v1/text-to-speech/{quote(voice_id, safe="")}'
    try:
        with httpx.Client(base_url=API_BASE, timeout=90, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', path, headers={'xi-api-key': key},
                               json={'text': text, 'model_id': 'eleven_multilingual_v2',
                                     'output_format': 'mp3_44100_128'}) as response:
                if response.status_code >= 400:
                    raise ValueError(f'ElevenLabs không tạo được giọng (HTTP {response.status_code}). Hãy kiểm tra gói, voice ID và hạn mức.')
                total = 0
                with open(filename, 'wb') as output:
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_AUDIO_BYTES:
                            raise ValueError('Âm thanh ElevenLabs vượt kích thước cho phép.')
                        output.write(chunk)
        if os.path.getsize(filename) < 300:
            raise ValueError('ElevenLabs trả dữ liệu âm thanh trống.')
    except httpx.RequestError as exc:
        raise ValueError('ElevenLabs bị gián đoạn kết nối trong lúc tạo giọng.') from exc
    return filename
