#!/usr/bin/env bash
# ============================================================
#  run_bot.sh — Linux/macOS bot launcher with venv support
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Activate venv if it exists ───────────────────────────────
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "[run] Using .venv Python: $(which python)"
elif [ -d "venv" ]; then
    source venv/bin/activate
    echo "[run] Using venv Python: $(which python)"
else
    echo "[run] No .venv found, using system Python: $(which python3 || which python)"
fi

# ── Check .env ───────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "[ERROR] .env file not found!"
    echo "        Copy .env.example to .env and fill in DISCORD_TOKEN"
    exit 1
fi

# ── Run the bot ──────────────────────────────────────────────
echo "[run] Starting Discord Music Bot..."
exec python bot.py
