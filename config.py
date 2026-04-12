import os
import ssl
from dotenv import load_dotenv

load_dotenv()


class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

    FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')
    SKIP_VOTE_THRESHOLD = int(os.getenv('SKIP_VOTE_THRESHOLD', '50'))
    DJ_ROLE_NAME = os.getenv('DJ_ROLE_NAME', 'DJ')
    MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '100'))
    DEFAULT_VOLUME = int(os.getenv('DEFAULT_VOLUME', '50'))
    SSL_VERIFY = os.getenv('SSL_VERIFY', 'true').lower() == 'true'

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
        'js_runtimes': {'deno': {'path': r'C:\Users\TinKan\AppData\Local\Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe\deno.exe'}},
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    @classmethod
    def setup_ssl(cls):
        if not cls.SSL_VERIFY:
            ssl._create_default_https_context = ssl._create_unverified_context
            orig_ssl_create = ssl.create_default_context

            def _unverified_ssl_context(*args, **kwargs):
                ctx = orig_ssl_create(*args, **kwargs)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                return ctx

            ssl.create_default_context = _unverified_ssl_context

    @classmethod
    def validate(cls):
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN not set in .env")