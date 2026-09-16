#!/usr/bin/env sh
# GET a public Binance USD(S)-M futures path for response-shape checks (read-only, no key).
# usage: scripts/fapi_get.sh /fapi/v1/premiumIndex symbol=BTCUSDT [key=value ...]
set -eu
path="${1:?path required, e.g. /fapi/v1/premiumIndex}"
shift
base="${BINANCE_BASE_URL:-https://fapi.binance.com}"
query=""
for kv in "$@"; do
  query="${query}${query:+&}${kv}"
done
url="${base}${path}${query:+?${query}}"
curl -sS --max-time 15 "$url"
echo
