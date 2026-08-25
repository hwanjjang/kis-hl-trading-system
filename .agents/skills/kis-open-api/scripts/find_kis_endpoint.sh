#!/usr/bin/env bash
# Search the official KIS sample repo (examples_llm) for an endpoint by keyword,
# TR ID, URL fragment, or Korean title, and print matching sample file paths.
#
# Usage:
#   find_kis_endpoint.sh <keyword>          # grep examples_llm, print matches
#   find_kis_endpoint.sh --show <keyword>   # also print the first matching sample file
#   find_kis_endpoint.sh --inventory        # regenerate the markdown inventory table
#
# The upstream repo is cloned shallowly into $KIS_UPSTREAM_DIR
# (default: /tmp/kis-open-trading-api) on first use.
set -euo pipefail

UPSTREAM_URL="https://github.com/koreainvestment/open-trading-api.git"
UPSTREAM_DIR="${KIS_UPSTREAM_DIR:-/tmp/kis-open-trading-api}"

ensure_clone() {
  if [ ! -d "$UPSTREAM_DIR/examples_llm" ]; then
    echo "Cloning $UPSTREAM_URL into $UPSTREAM_DIR ..." >&2
    git clone --depth 1 --quiet "$UPSTREAM_URL" "$UPSTREAM_DIR"
  fi
}

inventory() {
  python3 - "$UPSTREAM_DIR/examples_llm" <<'PY'
import re, sys, pathlib
root = pathlib.Path(sys.argv[1])
TR = re.compile(r'"((?:FH|HH|CT|TT|VT|JT|H0|HD)[A-Z0-9]{6,11})"')
print("| category | upstream folder | path | tr_id(s) | title |")
print("|---|---|---|---|---|")
for f in sorted(root.rglob("*.py")):
    # skip the chk_<endpoint>.py test file, but keep endpoints whose own folder starts with chk_ (chk_holiday)
    if f.name == "chk_" + f.parent.name + ".py" or f.name == "kis_auth.py":
        continue
    src = f.read_text(encoding="utf-8", errors="ignore")
    url = re.search(r'API_URL\s*=\s*"([^"]+)"', src)
    title = re.search(r'#\s*\[([^\]]+)\]\s*([^\n]*?)\s*>\s*([^\n\[]+)', src)
    ids = sorted(set(i for i in TR.findall(src) if not re.match(r'^KR\d', i)))
    row = (f.parts[-3], f.parts[-2], url.group(1) if url else "(websocket)",
           ", ".join(ids), title.group(3).strip() if title else "")
    print("| " + " | ".join(x.replace("|", "\\|") for x in row) + " |")
PY
}

main() {
  ensure_clone
  case "${1:-}" in
    "" | -h | --help)
      sed -n '2,12p' "$0"; exit 0 ;;
    --inventory)
      inventory; exit 0 ;;
    --show)
      shift
      keyword="${1:?keyword required}"
      first="$(grep -rli --include='*.py' -- "$keyword" "$UPSTREAM_DIR/examples_llm" | grep -v '/chk_' | sort | head -n 1 || true)"
      if [ -z "$first" ]; then echo "No sample matches '$keyword'" >&2; exit 1; fi
      echo "== $first"; cat "$first"; exit 0 ;;
  esac
  keyword="$1"
  grep -rli --include='*.py' -- "$keyword" "$UPSTREAM_DIR/examples_llm" \
    | grep -v '/chk_' | sort | sed "s|$UPSTREAM_DIR/||"
}

main "$@"
