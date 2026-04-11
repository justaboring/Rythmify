import json
import os

STORE_FILE = "panel_store.json"


def _load() -> dict:
    if os.path.exists(STORE_FILE):
        try:
            with open(STORE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    with open(STORE_FILE, "w") as f:
        json.dump(data, f)


def get_panel(guild_id: int) -> dict | None:
    """Return {'channel_id': int, 'message_id': int} or None."""
    data = _load()
    return data.get(str(guild_id))


def set_panel(guild_id: int, channel_id: int, message_id: int):
    data = _load()
    data[str(guild_id)] = {"channel_id": channel_id, "message_id": message_id}
    _save(data)


def clear_panel(guild_id: int):
    data = _load()
    data.pop(str(guild_id), None)
    _save(data)
