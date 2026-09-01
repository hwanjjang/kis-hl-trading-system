#!/usr/bin/env bash
# Fetch a page of the official Hyperliquid docs as markdown.
#
# Usage:
#   fetch_hl_docs.sh --list                  # print the docs page index (llms.txt)
#   fetch_hl_docs.sh <page>                  # e.g. exchange-endpoint, info-endpoint/spot
#   fetch_hl_docs.sh --url <full-url>        # any docs URL, .md is appended if missing
#   fetch_hl_docs.sh --grep <pattern> <page> # fetch then grep with 3 lines of context
#
# <page> is relative to .../hyperliquid-docs/for-developers/api/ unless it already
# contains a slash prefix handled below. Output goes to stdout; pipe it to a pager.
set -euo pipefail

DOCS_ROOT="https://hyperliquid.gitbook.io/hyperliquid-docs"
API_ROOT="$DOCS_ROOT/for-developers/api"

fetch() {
  curl -fsSL --max-time 30 "$1"
}

resolve_url() {
  local page="$1"
  case "$page" in
    http*) printf '%s' "$page" ;;
    hyperliquid-improvement-proposals-hips/*|for-developers/*|trading/*)
      printf '%s/%s' "$DOCS_ROOT" "$page" ;;
    *) printf '%s/%s' "$API_ROOT" "$page" ;;
  esac
}

main() {
  case "${1:-}" in
    "" | -h | --help)
      sed -n '2,11p' "$0"; exit 0 ;;
    --list)
      fetch "$DOCS_ROOT/llms.txt"; exit 0 ;;
    --url)
      shift; page="${1:?url required}" ;;
    --grep)
      shift
      pattern="${1:?pattern required}"; shift
      page="${1:?page required}"
      url="$(resolve_url "$page")"
      [ "${url%.md}" = "$url" ] && url="$url.md"
      fetch "$url" | grep -i -C 3 -- "$pattern" \
        || { echo "No match for '$pattern' in $url" >&2; exit 1; }
      exit 0 ;;
    *)
      page="$1" ;;
  esac

  url="$(resolve_url "$page")"
  [ "${url%.md}" = "$url" ] && url="$url.md"
  fetch "$url"
}

main "$@"
