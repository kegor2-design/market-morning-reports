#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
set +a

CODEX_BIN="${MMP_CODEX_BIN:-codex}"
command -v "$CODEX_BIN" >/dev/null 2>&1 || { echo "[FAIL] Codex executable not found: $CODEX_BIN" >&2; exit 2; }
"$CODEX_BIN" --version
"$CODEX_BIN" exec --help | grep -F -- "--output-schema" >/dev/null
"$CODEX_BIN" exec --help | grep -F -- "--ephemeral" >/dev/null
python3 -m json.tool "$PROJECT_DIR/config/codex_analysis_schema.json" >/dev/null
echo "[OK] Codex executable and analysis schema are ready"
