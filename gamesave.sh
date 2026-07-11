#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# gamesave.sh — Game Save Guardian for Rythmify
#
# A utility script that snapshots the bot's runtime state (audit log, queue,
# playlists, panel store, recommendation data) into a dated archive so you
# can roll back after testing new features or before a risky upgrade.
#
# Usage:
#   ./gamesave.sh [--dry-run] [--keep N]
#
# Options:
#   --dry-run   Show what would be archived without writing anything.
#   --keep N    Keep only the N most recent saves (deletes older ones).
#               Default: 5.  Set to 0 to keep all.
#
# Files archived:
#   audit_log.json, spotify_tokens.json, playlists.json,
#   panel_store.json, request_channel_store.json,
#   quality_settings.json, stats_store.json,
#   recommendations.json, recommendation_interactions.json,
#   restart_state.json
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAVE_DIR="${SCRIPT_DIR}/gamesaves"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_NAME="rythmify-save-${TIMESTAMP}.tar.gz"
KEEP=5
DRY_RUN=false

# ── Parse arguments ──────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  DRY_RUN=true; shift ;;
    --keep)     KEEP="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--dry-run] [--keep N]"
      echo ""
      echo "Game Save Guardian — snapshot Rythmify runtime state."
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Files to archive ─────────────────────────────────────────────────────

FILES=(
  "audit_log.json"
  "spotify_tokens.json"
  "playlists.json"
  "panel_store.json"
  "request_channel_store.json"
  "quality_settings.json"
  "stats_store.json"
  "recommendations.json"
  "recommendation_interactions.json"
  "restart_state.json"
)

EXISTING=()
for f in "${FILES[@]}"; do
  [[ -f "${SCRIPT_DIR}/${f}" ]] && EXISTING+=("${f}")
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  echo "⚠️  No state files found in ${SCRIPT_DIR} — nothing to archive."
  exit 0
fi

# ── Create save directory ───────────────────────────────────────────────

if [[ "$DRY_RUN" == true ]]; then
  echo "🧪 [DRY RUN] Would archive these files:"
  printf '   • %s\n' "${EXISTING[@]}"
  echo "   → ${SAVE_DIR}/${ARCHIVE_NAME}"
  exit 0
fi

mkdir -p "${SAVE_DIR}"

# ── Create archive (relative paths) ─────────────────────────────────────

echo "📦 Saving game state to ${ARCHIVE_NAME} ..."
tar -czf "${SAVE_DIR}/${ARCHIVE_NAME}" \
  --directory="${SCRIPT_DIR}" \
  "${EXISTING[@]}"

echo "✅ Saved: ${SAVE_DIR}/${ARCHIVE_NAME}"
echo "   Files archived: ${#EXISTING[@]}"

# ── Prune old saves ────────────────────────────────────────────────────

if [[ "$KEEP" -gt 0 ]]; then
  COUNT=$(ls -1 "${SAVE_DIR}"/rythmify-save-*.tar.gz 2>/dev/null | wc -l)
  if [[ "$COUNT" -gt "$KEEP" ]]; then
    TO_DELETE=$(( COUNT - KEEP ))
    echo "🧹 Pruning ${TO_DELETE} old save(s) (keeping ${KEEP})..."
    ls -1t "${SAVE_DIR}"/rythmify-save-*.tar.gz 2>/dev/null | tail -n "${TO_DELETE}" | while read -r old; do
      rm -f "${old}"
      echo "   🗑  Deleted: ${old}"
    done
  fi
fi

echo ""
echo "🎮 Game save complete. To restore:"
echo "   tar -xzf ${SAVE_DIR}/${ARCHIVE_NAME} -C ${SCRIPT_DIR}"
