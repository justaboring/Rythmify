import os
import ssl
import shutil
import platform
from dotenv import load_dotenv

load_dotenv()


# ── Module-level helpers (needed before class body evaluates) ────────────────

def _detect_arch_based() -> bool:
    """Return True if the current Linux distro is Arch-based."""
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
        arch_ids = {"arch", "cachyos", "manjaro", "endeavouros", "garuda", "artix", "arco", "parabola"}
        for line in content.splitlines():
            if line.startswith("id=") or line.startswith("id_like="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                for token in val.replace(",", " ").split():
                    if token in arch_ids:
                        return True
    except Exception:
        pass
    return False


def _find_ffmpeg() -> str:
    """
    Find FFmpeg executable across platforms.
    Priority:
      1. FFMPEG_PATH env var (explicit override)
      2. ffmpeg / ffmpeg.exe already on PATH
      3. Common Windows install locations
      4. Fallback to 'ffmpeg' (let OS resolve)
    """
    env_path = os.getenv('FFMPEG_PATH', '').strip()
    if env_path and env_path.lower() != 'auto':
        return env_path

    # Check PATH first (works on all OS)
    which = shutil.which('ffmpeg')
    if which:
        return which

    # Windows — check common install locations
    if platform.system() == "Windows":
        candidates = [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\ffmpeg\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
            r'C:\tools\ffmpeg\bin\ffmpeg.exe',   # Chocolatey default
            os.path.expanduser(r'~\ffmpeg\bin\ffmpeg.exe'),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

    # Linux — check common locations (usually already on PATH, but just in case)
    if platform.system() == "Linux":
        for path in ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/opt/bin/ffmpeg']:
            if os.path.isfile(path):
                return path

    return 'ffmpeg'  # final fallback


class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
    # ── Platform detection ──────────────────────────────────────────────────
    _system    = platform.system()      # 'Linux', 'Windows', 'Darwin'
    is_windows = _system == "Windows"
    is_linux   = _system == "Linux"
    is_mac     = _system == "Darwin"
    is_arch_based: bool = (_system == "Linux") and _detect_arch_based()

    # ── FFmpeg path ─────────────────────────────────────────────────────────
    FFMPEG_PATH: str = _find_ffmpeg()

    SKIP_VOTE_THRESHOLD = int(os.getenv('SKIP_VOTE_THRESHOLD', '50'))
    DJ_ROLE_NAME        = os.getenv('DJ_ROLE_NAME', 'DJ')
    MAX_QUEUE_SIZE      = int(os.getenv('MAX_QUEUE_SIZE', '100'))
    DEFAULT_VOLUME      = int(os.getenv('DEFAULT_VOLUME', '50'))
    SSL_VERIFY          = os.getenv('SSL_VERIFY', 'true').lower() == 'true'

    YTDL_FORMAT_OPTIONS = {
        'format': 'bestaudio/best',
        'extract_flat': False,
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': False,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'legacyserverconnect': True,
        'force-ipv4': True,
        'cachedir': False,
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    @classmethod
    def get_system_info(cls) -> dict:
        """Return a dict of system info for diagnostics."""
        return {
            "os":         cls._system,
            "os_version": platform.version(),
            "arch":       platform.machine(),
            "python":     platform.python_version(),
            "arch_based": cls.is_arch_based,
            "ffmpeg":     cls.FFMPEG_PATH,
        }

    @classmethod
    def setup_ssl(cls):
        if not cls.SSL_VERIFY:
            ssl._create_default_https_context = ssl._create_unverified_context
            orig_ssl_create = ssl.create_default_context

            def _unverified_ssl_context(*args, **kwargs):
                ctx = orig_ssl_create(*args, **kwargs)
                ctx.check_hostname = False
                ctx.verify_mode    = ssl.CERT_NONE
                return ctx

            ssl.create_default_context = _unverified_ssl_context

    @classmethod
    def validate(cls):
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN not set in .env")

        info = cls.get_system_info()
        distro_label = " (Arch-based)" if info["arch_based"] else ""
        print(f"[Config] OS      : {info['os']}{distro_label}")
        print(f"[Config] Python  : {info['python']}")
        print(f"[Config] FFmpeg  : {info['ffmpeg']}")