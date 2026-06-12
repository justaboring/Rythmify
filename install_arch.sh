#!/usr/bin/env bash
# ============================================================
#  install_arch.sh — Arch-based Linux installer
#  Supports: CachyOS, Arch Linux, Manjaro, EndeavourOS, Garuda, Artix
# ============================================================
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}================================================${NC}"
echo -e "${BOLD}  Discord Music Bot — Arch/CachyOS Installer${NC}"
echo -e "${BOLD}================================================${NC}"

# ── Check we're on Arch-based ────────────────────────────────
if ! command -v pacman &>/dev/null; then
    echo -e "${RED}[ERROR] pacman not found. This script is for Arch-based distros only.${NC}"
    echo "        Supported: CachyOS, Arch, Manjaro, EndeavourOS, Garuda, Artix"
    echo "        For other Linux: sudo apt install python3 python3-pip ffmpeg opus"
    exit 1
fi

DISTRO=$(grep -oP '(?<=^ID=).+' /etc/os-release 2>/dev/null | tr -d '"' || echo "arch")
echo -e "${GREEN}  Detected distro: ${DISTRO}${NC}"

# ── 1. System packages via pacman ────────────────────────────
echo -e "\n${BOLD}[1/4] Installing system dependencies (pacman)...${NC}"
sudo pacman -S --needed --noconfirm \
    python \
    python-pip \
    python-virtualenv \
    ffmpeg \
    opus \
    git

echo -e "${GREEN}  [OK] System packages installed${NC}"

# ── 2. Check for AUR helper (optional, for ytmusicapi if needed) ─
echo -e "\n${BOLD}[2/4] Checking AUR helper...${NC}"
if command -v yay &>/dev/null; then
    echo -e "${GREEN}  [OK] yay found${NC}"
elif command -v paru &>/dev/null; then
    echo -e "${GREEN}  [OK] paru found${NC}"
else
    echo -e "${YELLOW}  [INFO] No AUR helper found (yay/paru). Not required.${NC}"
fi

# ── 3. Python virtual environment ───────────────────────────
echo -e "\n${BOLD}[3/4] Setting up Python virtual environment...${NC}"

# Arch uses PEP 668 — venv is required for pip installs
if [ ! -d ".venv" ]; then
    python -m venv .venv
    echo -e "${GREEN}  [OK] Created .venv${NC}"
else
    echo -e "${YELLOW}  [INFO] .venv already exists, reusing it${NC}"
fi

# Activate and install
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}  [OK] Python dependencies installed${NC}"

# ── 4. .env setup ───────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Environment setup...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}  [ACTION REQUIRED] .env created from template.${NC}"
    echo -e "${YELLOW}  Edit .env and add your DISCORD_TOKEN:${NC}"
    echo -e "${YELLOW}    nano .env${NC}"
else
    echo -e "${GREEN}  [OK] .env already exists${NC}"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""
echo "  Next steps:"
echo "  1. Edit .env → set your DISCORD_TOKEN"
echo "  2. Run:  ./run_bot.sh"
echo "  3. Run diagnostics: .venv/bin/python diagnose.py"
echo ""
