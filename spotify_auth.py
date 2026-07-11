"""
spotify_auth.py — Spotify OAuth for user-level Spotify Connect.

Stores per-user Spotify tokens in spotify_tokens.json.
Provides an aiohttp-based OAuth callback server so users can link their
Spotify account in Discord via `/spotify connect`.

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env (already used
by spotify_module.py for client-credentials flow).  Redirect URI defaults to
http://localhost:8889/callback.  Set SPOTIFY_REDIRECT_URI in .env to override.
"""

import os
import json
import time
import asyncio
import hashlib
import secrets
import threading
from typing import Optional

import aiohttp
import aiohttp.web

from config import Config

SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:8889/callback"
)
TOKEN_PATH = "spotify_tokens.json"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"

# In-memory cache: {user_id: token_dict}
_tokens: dict[int, dict] = {}
_lock = threading.Lock()


# ── Persistence ─────────────────────────────────────────────────────────────

def _load_tokens() -> dict:
    if not os.path.exists(TOKEN_PATH):
        return {}
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_tokens() -> None:
    tmp = TOKEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_tokens, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TOKEN_PATH)


def _ensure_loaded() -> None:
    if not _tokens:
        _tokens.update(_load_tokens())


# ── Public API ──────────────────────────────────────────────────────────────

def get_user_token(user_id: int) -> Optional[dict]:
    """Return stored token dict for a user, or None."""
    _ensure_loaded()
    data = _tokens.get(str(user_id))
    if data is None:
        return None
    # Check expiry — if stale, caller should refresh
    if data.get("expires_at", 0) < time.time() + 60:
        return None  # expired / about to expire
    return dict(data)


def store_user_token(user_id: int, token_data: dict) -> None:
    """Store or update a user's token dict."""
    _ensure_loaded()
    if "expires_at" not in token_data:
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    _tokens[str(user_id)] = token_data
    _save_tokens()


def remove_user_token(user_id: int) -> bool:
    """Remove a user's token. Returns True if existed."""
    _ensure_loaded()
    key = str(user_id)
    if key in _tokens:
        del _tokens[key]
        _save_tokens()
        return True
    return False


def has_user_token(user_id: int) -> bool:
    """Check if user has a valid stored token."""
    return get_user_token(user_id) is not None


async def refresh_user_token(user_id: int) -> Optional[dict]:
    """Attempt to refresh a stored token.  Returns fresh token or None."""
    _ensure_loaded()
    data = _tokens.get(str(user_id))
    if not data or "refresh_token" not in data:
        return None

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": data["refresh_token"],
        "client_id": Config.SPOTIFY_CLIENT_ID,
        "client_secret": Config.SPOTIFY_CLIENT_SECRET,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://accounts.spotify.com/api/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                return None
            new_data = await resp.json()

    new_data["refresh_token"] = new_data.get("refresh_token", data["refresh_token"])
    new_data["expires_at"] = time.time() + new_data.get("expires_in", 3600)
    _tokens[str(user_id)] = new_data
    _save_tokens()
    return new_data


# ── OAuth URL generation ────────────────────────────────────────────────────

def build_authorize_url(user_id: int) -> str:
    """Build the Spotify OAuth authorize URL for a given Discord user."""
    state = hashlib.sha256(f"{user_id}:{secrets.token_hex(16)}".encode()).hexdigest()
    params = {
        "response_type": "code",
        "client_id": Config.SPOTIFY_CLIENT_ID,
        "scope": SCOPES,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "state": state,
        "show_dialog": "true",
    }
    # Temporarily store the state → user_id mapping
    _state_map[state] = user_id
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://accounts.spotify.com/authorize?{qs}"


# In-memory state → user_id mapping for OAuth handshake
_state_map: dict[str, int] = {}


async def exchange_code(code: str, state: str) -> Optional[int]:
    """Exchange an auth code for tokens. Returns the user_id on success."""
    user_id = _state_map.pop(state, None)
    if user_id is None:
        return None

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": Config.SPOTIFY_CLIENT_ID,
        "client_secret": Config.SPOTIFY_CLIENT_SECRET,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://accounts.spotify.com/api/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                return None
            token_data = await resp.json()

    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    store_user_token(user_id, token_data)
    return user_id


# ── OAuth Callback Server ───────────────────────────────────────────────────

# Single-event bridge between the aiohttp callback handler and the Discord
# user waiting for their /spotify connect command.
_pending: dict[int, asyncio.Future] = {}


async def _callback_handler(request):
    """aiohttp request handler for the OAuth redirect."""
    code = request.query.get("code")
    state = request.query.get("state")
    error = request.query.get("error")

    if error or not code or not state:
        text = "<html><body><h2>❌ Authorization failed.</h2><p>You may close this tab.</p></body></html>"
        return aiohttp.web.Response(text=text, content_type="text/html")

    user_id = await exchange_code(code, state)
    if user_id is None:
        text = "<html><body><h2>❌ Could not link your account. Try again.</h2></body></html>"
        return aiohttp.web.Response(text=text, content_type="text/html")

    # Resolve the pending future
    fut = _pending.pop(user_id, None)
    if fut and not fut.done():
        fut.set_result(True)

    text = "<html><body><h2>✅ Spotify account linked! You may close this tab.</h2></body></html>"
    return aiohttp.web.Response(text=text, content_type="text/html")


_callback_server: Optional[aiohttp.web.AppRunner] = None


async def start_callback_server() -> None:
    """Start the aiohttp server that handles Spotify OAuth callbacks."""
    global _callback_server
    if _callback_server is not None:
        return

    app = aiohttp.web.Application()
    app.router.add_get("/callback", _callback_handler)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    # Parse port from redirect URI
    port = 8889
    if ":" in SPOTIFY_REDIRECT_URI:
        parts = SPOTIFY_REDIRECT_URI.split(":")
        if len(parts) >= 3:
            try:
                port = int(parts[2].split("/")[0])
            except ValueError:
                pass
    site = aiohttp.web.TCPSite(runner, "localhost", port)
    await site.start()
    _callback_server = runner
    print(f"[spotify_auth] OAuth callback server listening on localhost:{port}")


async def stop_callback_server() -> None:
    """Shut down the OAuth callback server."""
    global _callback_server
    if _callback_server:
        await _callback_server.cleanup()
        _callback_server = None


async def wait_for_callback(user_id: int, timeout: float = 120.0) -> bool:
    """Wait for the user to complete OAuth in their browser. Returns True on success."""
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending[user_id] = fut
    try:
        await asyncio.wait_for(fut, timeout=timeout)
        return True
    except asyncio.TimeoutError:
        _pending.pop(user_id, None)
        return False
