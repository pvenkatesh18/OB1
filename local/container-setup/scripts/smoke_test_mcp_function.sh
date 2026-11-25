#!/usr/bin/env bash
# Smoke-test an OB1 MCP edge function locally: method guard, key guard, tool registration.
#
#   bash smoke_test_mcp_function.sh <function-dir> [port]
#
# Runs the function on DUMMY Supabase credentials: these code paths never reach the
# database, so no real key and no store access are involved. Use it before deploying
# a staged function, so a broken auth or handshake path is caught on this machine
# instead of after a deploy.
#
# Expected: 405 on GET, 401 with no key and with a wrong key, then an initialize
# response and a tools/list listing exactly one tool. Anything else, or a hang,
# means stop and read the function's transport code.
set -u

DIR="${1:?usage: smoke_test_mcp_function.sh <function-dir> [port]}"
PORT="${2:-8000}"          # Deno.serve() with no arguments binds 8000
KEY="local-test-key"
LOG="/tmp/$(basename "$DIR").server.log"

[ -f "$DIR/index.ts" ] || { echo "no index.ts in $DIR"; exit 1; }
command -v deno >/dev/null || export PATH="/opt/data/.deno/bin:$PATH"
command -v deno >/dev/null || { echo "deno not on PATH — see references/open-brain-setup.md"; exit 1; }
export DENO_DIR="${DENO_DIR:-/opt/data/cache/deno}"

cd "$DIR" || exit 1
SUPABASE_URL="http://127.0.0.1:59999" \
SUPABASE_SERVICE_ROLE_KEY="dummy-service-role-key" \
OPENROUTER_API_KEY="" \
MCP_ACCESS_KEY="$KEY" \
  deno run --allow-net --allow-env --allow-read index.ts >"$LOG" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/" && break
  sleep 0.5
done

U="http://127.0.0.1:$PORT/"
CT='content-type: application/json'
AC='accept: application/json, text/event-stream'

echo "--- 1. GET / (expect 405) ---"
curl -s -m 5 -o /dev/null -w 'http %{http_code}\n' "$U"

echo "--- 2. POST no key (expect 401) ---"
curl -s -m 5 -w '\nhttp %{http_code}\n' -X POST "$U" -H "$CT" -H "$AC" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

echo "--- 3. POST wrong key (expect 401) ---"
curl -s -m 5 -w '\nhttp %{http_code}\n' -X POST "$U" -H "$CT" -H 'x-brain-key: wrong' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

echo "--- 4. POST initialize (expect a serverInfo result) ---"
curl -s -m 10 -X POST "$U" -H "$CT" -H "x-brain-key: $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' | head -c 600
echo
echo "--- 5. POST tools/list (expect the tool schema) ---"
curl -s -m 10 -X POST "$U" -H "$CT" -H "x-brain-key: $KEY" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | head -c 2500
echo
echo "--- server log ---"
tail -3 "$LOG"
