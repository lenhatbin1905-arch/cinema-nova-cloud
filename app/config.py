from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv('VIETFRAME_DATA', str(PROJECT_ROOT / 'workspace'))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR = DATA_DIR / 'projects'
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'studio.sqlite3'
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', '350'))
MAX_DURATION_SECONDS = int(os.getenv('MAX_DURATION_SECONDS', '1800'))
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'small')
ENABLE_LOCAL_VIDEO_GEN = os.getenv('ENABLE_LOCAL_VIDEO_GEN', 'false').lower() == 'true'
VIDEO_MODEL_ID = os.getenv('VIDEO_MODEL_ID', 'THUDM/CogVideoX-2b')
KOKORO_TTS_URL = os.getenv('KOKORO_TTS_URL', '').rstrip('/')

KOKORO_TTS_API_KEY = os.getenv('KOKORO_TTS_API_KEY', '')

# If deploying remotely, set this to a long random value to unlock one-time account setup.
# Without a token, first-owner setup is restricted to loopback clients.
SETUP_TOKEN = os.getenv('VIETFRAME_SETUP_TOKEN', '')
# Set true behind an HTTPS reverse proxy. Cookies automatically use Secure for HTTPS requests.
COOKIE_SECURE = os.getenv('VIETFRAME_COOKIE_SECURE', 'false').lower() == 'true'
