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
while true; do
    echo "[run] Starting Discord Music Bot..."
    python bot.py
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[run] Manual restart requested. Resuming immediately..."
    elif [ $EXIT_CODE -eq 130 ]; then
        echo "[run] Interrupted by user. Exiting."
        exit 0
    else
        echo "[run] Bot crashed (Exit Code: $EXIT_CODE). Restarting in 5 seconds..."
        sleep 5
    fi
done
