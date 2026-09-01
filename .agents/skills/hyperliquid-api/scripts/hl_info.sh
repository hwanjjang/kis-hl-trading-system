#!/usr/bin/env bash
# POST a public read-only request to the Hyperliquid /info endpoint.
#
# Usage:
#   hl_info.sh '{"type":"metaAndAssetCtxs","dex":"xyz"}'
#   hl_info.sh '{"type":"l2Book","coin":"xyz:XYZ100"}' | python3 -m json.tool
#   HYPERLIQUID_BASE_URL=https://api.hyperliquid-testnet.xyz hl_info.sh '{"type":"allMids"}'
#
# /info is public and unauthenticated: no key, no signature, no wallet needed.
# This script refuses to touch /exchange. Placing, cancelling, or modifying an order
# must go through kis_hl's guarded order path, never through curl.
#
# Weighted rate limit is 1200 per minute per IP; do not loop this over a whole universe.
set -euo pipefail

BASE_URL="${HYPERLIQUID_BASE_URL:-https://api.hyperliquid.xyz}"
BODY="${1:-}"

if [ -z "$BODY" ] || [ "$BODY" = "-h" ] || [ "$BODY" = "--help" ]; then
  sed -n '2,13p' "$0"
  exit 0
fi

if ! printf '%s' "$BODY" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  echo "Body is not valid JSON: $BODY" >&2
  exit 1
fi

if ! printf '%s' "$BODY" | grep -q '"type"'; then
  echo 'Body must contain a "type" field, e.g. {"type":"allMids"}' >&2
  exit 1
fi

curl -fsSL --max-time 30 \
  -X POST "${BASE_URL%/}/info" \
  -H 'Content-Type: application/json' \
  -d "$BODY"
echo
