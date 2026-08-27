#!/usr/bin/env bash
set -Eeuo pipefail
URL="${1:-${MMP_BLOG_PUBLIC_URL:-}}"
[[ -n "$URL" ]] || { echo "usage: $0 https://your-blog.blogspot.com/"; exit 2; }
command -v curl >/dev/null 2>&1 || { echo '[FAIL] curl required'; exit 2; }
TMP="$(mktemp /tmp/mmp-live-theme.XXXXXX.html)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL --max-time 20 "$URL" -o "$TMP"
for marker in 'rp-site-header' 'rp-home-portal' "data-rp-theme='1.6.5'" 'decorateResearchCards'; do
  if ! grep -Fq "$marker" "$TMP"; then
    echo "[FAIL] live Blogger page does not contain Research Portal Hotfix marker: $marker"
    echo "[INFO] Server code may be deployed while Blogger Theme is still old/unfixed."
    exit 3
  fi
done
if ! grep -Eq 'rp-home[^}]{0,900}post-body' "$TMP"; then
  echo '[FAIL] live Theme does not expose homepage full-post suppression CSS.'
  exit 4
fi
if ! grep -Eq 'rp-home[^}]{0,1800}post-share-buttons|post-share-buttons[^}]{0,1800}display:none' "$TMP"; then
  echo '[FAIL] live Theme does not expose homepage share suppression CSS.'
  exit 5
fi
echo "[PASS] live Blogger Research Portal 1.6.5 markers detected: $URL"
