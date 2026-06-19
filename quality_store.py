import json
import os
from typing import Dict, Optional
from config import Config

QUALITY_STORE_FILE = "quality_settings.json"
AUDIT_LOG_FILE = "quality_audit.log"

def _load_quality_store() -> Dict[int, str]:
    """Load quality settings from file."""
    if not os.path.exists(QUALITY_STORE_FILE):
        return {}
    try:
        with open(QUALITY_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convert string keys back to int
            return {int(k): v for k, v in data.items()}
    except Exception:
        return {}

def _save_quality_store(data: Dict[int, str]) -> None:
    """Save quality settings to file."""
    with open(QUALITY_STORE_FILE, "w", encoding="utf-8") as f:
        # Convert int keys to str for JSON serialization
        json.dump({str(k): v for k, v in data.items()}, f, indent=2)

def _log_audit(guild_id: int, guild_name: str, user_id: int, user_name: str, old_quality: Optional[str], new_quality: str) -> None:
    """Log quality change for auditing."""
    import datetime
    timestamp = datetime.datetime.now().isoformat()
    log_entry = f"[{timestamp}] Guild: {guild_id} ({guild_name}) | User: {user_id} ({user_name}) | Change: {old_quality} -> {new_quality}\n"
    
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"[QualityStore] Failed to write audit log: {e}")

def get_quality(guild_id: int) -> str:
    """Get quality setting for a guild. Returns default if not set."""
    store = _load_quality_store()
    quality = store.get(guild_id, Config.DEFAULT_QUALITY)
    # Validate quality exists, fallback to default if invalid
    if quality not in Config.VOICE_QUALITY_PRESETS:
        return Config.DEFAULT_QUALITY
    return quality

def set_quality(guild_id: int, guild_name: str, quality: str, user_id: int, user_name: str) -> bool:
    """Set quality setting for a guild. Returns True if changed."""
    if quality not in Config.VOICE_QUALITY_PRESETS:
        return False
    
    store = _load_quality_store()
    old_quality = store.get(guild_id, None)
    
    if old_quality == quality:
        return False  # No change needed
    
    store[guild_id] = quality
    _save_quality_store(store)
    _log_audit(guild_id, guild_name, user_id, user_name, old_quality, quality)
    return True

def get_all_qualities() -> Dict[int, str]:
    """Get all quality settings."""
    return _load_quality_store()
