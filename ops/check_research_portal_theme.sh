#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PYTHON="${MMP_PYTHON:-python3}"
THEME="$ROOT/blogger_theme/market_morning_research_portal.xml"
[[ -f "$THEME" ]] || { echo "[FAIL] theme missing: $THEME"; exit 2; }
"$PYTHON" - "$ROOT" <<'PY'
import sys
from pathlib import Path
root=Path(sys.argv[1])
sys.path.insert(0,str(root))
from market_morning_publisher.research_portal import validate_theme, load_portal_config
r=validate_theme(root/'blogger_theme/market_morning_research_portal.xml')
assert r.ok, r
cfg=load_portal_config(root)
assert cfg['design_direction']=='ASSET_MANAGER_RESEARCH_PORTAL'
assert cfg['theme_application']['blogger_api_supports_theme_write'] is False
assert cfg['release']=='1.6.5'
assert r.blogger_css_enabled
assert r.has_home_post_suppression
assert r.has_share_suppression
theme=(root/'blogger_theme/market_morning_research_portal.xml').read_text(encoding='utf-8')
assert "line.title=ev.name" in theme
assert "/search?q=우리의+모닝브리핑&amp;by-date=true&amp;max-results=1" in theme
assert "/search/label/Market%20View" in theme
print('[OK] research portal theme contract')
PY
OUT="$(mktemp /tmp/mmp-research-portal-preview.XXXXXX.html)"
"$PYTHON" "$ROOT/ops/render_research_portal_preview.py" --root "$ROOT" --output "$OUT" >/dev/null
for marker in 'rp-site-header' 'rp-home-portal' 'rp-market-board' 'rp-intelligence' 'mmp-responsive' 'post-share-buttons' 'sharing-platform-button'; do
  grep -q "$marker" "$OUT" || { echo "[FAIL] preview marker missing: $marker"; exit 3; }
done
echo "[PASS] Research Portal theme + preview: $OUT"
