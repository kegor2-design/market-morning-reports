#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
set +a
[[ -n "${MMP_PUBLIC_REPO_DIR:-}" && -d "$MMP_PUBLIC_REPO_DIR/.git" ]] || {
  echo "[FAIL] invalid MMP_PUBLIC_REPO_DIR" >&2
  exit 2
}

"$PROJECT_DIR/ops/run_market_history.sh" "$PROJECT_DIR" "$ENV_FILE"
mkdir -p "$MMP_PUBLIC_REPO_DIR/market-history"
cp -pR "$PROJECT_DIR/public/market-history/." "$MMP_PUBLIC_REPO_DIR/market-history/"

git -C "$MMP_PUBLIC_REPO_DIR" add market-history
if git -C "$MMP_PUBLIC_REPO_DIR" diff --cached --quiet; then
  echo "[OK] market history source unchanged"
else
  git -C "$MMP_PUBLIC_REPO_DIR" commit -m "data: update long-run market history"
  git -C "$MMP_PUBLIC_REPO_DIR" push
fi

python3 "$PROJECT_DIR/ops/publish_market_history_page.py"
