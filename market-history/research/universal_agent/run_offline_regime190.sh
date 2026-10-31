#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT=/home/kegor2/market-morning-reports
STATE=/home/kegor2/MyDream2000/research/universal_agent/regime190-offline
cd "$ROOT/market-history/research"
exec /usr/bin/timeout --signal=TERM --kill-after=10s 150s \
  /home/kegor2/stock_env/bin/python -m universal_agent.offline_worker run \
  --state-dir "$STATE" --repo "$ROOT" --max-tasks 3 --max-seconds 120
