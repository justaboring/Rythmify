import json
import os

STORE_FILE = "request_channel_store.json"


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


def get_request_channel(guild_id: int) -> int | None:
    data = _load()
    val = data.get(str(guild_id))
    return int(val) if val else None


def set_request_channel(guild_id: int, channel_id: int):
    data = _load()
    data[str(guild_id)] = channel_id
    _save(data)


def clear_request_channel(guild_id: int):
    data = _load()
    data.pop(str(guild_id), None)
    _save(data)
