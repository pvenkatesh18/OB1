#!/usr/bin/env bash
# Deploy the two OB1 write-path MCP functions to Poorna's Supabase project.
#
#   update-thought-mcp : adds update_thought(id, content?, metadata_patch?, if_unchanged_since?)
#   delete-thought-mcp : adds delete_thought(id)  -- HARD delete, no undo
#
# Both are unmodified upstream files from integrations/ in NateBJones-Projects/OB1.
# Staged (byte-identical to upstream) at supabase/functions/<name>/index.ts.
#
# NOT NEEDED for Hermes: the already-deployed open-brain-rest function has
# PUT/DELETE /thought/:id, so Hermes corrects and removes entries through
# skills/productivity/personal-knowledge-capture/scripts/ob_admin.py.
# These deploys are only for MCP-only clients: Claude Desktop, Claude Code,
# ChatGPT, Codex.
#
# Requires: supabase CLI, and either `supabase login` or SUPABASE_ACCESS_TOKEN.
# `supabase functions deploy --project-ref <ref>` needs only the access token;
# it does NOT need the database password.
#
# Run from the repo root:  bash deploy-ob-admin-functions.sh
set -euo pipefail

PROJECT_REF="byawvafeuychywyigxsn"   # PV- Open Brain
REPO_DIR="/opt/data/projects/OB1"

cd "$REPO_DIR"
command -v supabase >/dev/null || { echo "supabase CLI not found: npm i -g supabase"; exit 1; }

echo "== type-check both functions locally first =="
for fn in update-thought-mcp delete-thought-mcp; do
  ( cd "supabase/functions/$fn" && deno check index.ts )
done

echo "== deploy (secrets MCP_ACCESS_KEY + OPENROUTER_API_KEY are already project-level) =="
supabase functions deploy update-thought-mcp --project-ref "$PROJECT_REF" --no-verify-jwt
supabase functions deploy delete-thought-mcp --project-ref "$PROJECT_REF" --no-verify-jwt

echo "== verify: auth guard, method guard, tool registration =="
KEY=$(grep -E '^OB_MCP_KEY=' "${HERMES_HOME:-/opt/data}/.env" | cut -d= -f2- | tr -d '"'"'"'')
for fn in update-thought-mcp delete-thought-mcp; do
  U="https://${PROJECT_REF}.supabase.co/functions/v1/${fn}"
  echo "--- $fn"
  echo -n "  no key (expect 401):   "; curl -s -o /dev/null -w '%{http_code}\n' -X POST "$U" -H 'content-type: application/json' -d '{}'
  echo -n "  with key (tools/list): "; curl -s -m 30 -X POST "$U" -H "x-brain-key: $KEY" -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 200; echo
done

cat <<'EOF'

== register in Hermes (custom header — the Bearer trap: `hermes mcp add --auth header`
   would write Authorization: Bearer and OB1 rejects it) ==
hermes config set mcp_servers.open_brain_update.url 'https://byawvafeuychywyigxsn.supabase.co/functions/v1/update-thought-mcp'
hermes config set mcp_servers.open_brain_update.headers.x-brain-key '${OB_MCP_KEY}'
hermes config set mcp_servers.open_brain_delete.url 'https://byawvafeuychywyigxsn.supabase.co/functions/v1/delete-thought-mcp'
hermes config set mcp_servers.open_brain_delete.headers.x-brain-key '${OB_MCP_KEY}'
hermes mcp test open_brain_update
hermes mcp test open_brain_delete

Then add the same two URLs (?key=<MCP_ACCESS_KEY>) as custom connectors in
Claude Desktop / ChatGPT if you want the write path there too.
EOF
