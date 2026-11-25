# Wiring Open Brain (OB1) into Hermes

Open Brain = Nate B. Jones's OB1 (https://github.com/NateBJones-Projects/OB1) — a Supabase Edge Function that exposes a personal thought store over MCP. Poorna's instance is the OB1 core server, which this identifies from its forks by the tool set `capture_thought` / `search_thoughts` / `list_thoughts` / `thought_stats`.

## Endpoint shape

    https://<project-ref>.supabase.co/functions/v1/open-brain-mcp

That is Streamable HTTP (the server uses `StreamableHTTPTransport` from `@hono/mcp`), so Hermes' default HTTP transport is right — do not set `transport: sse`.

## The auth trap

OB1 reads its key from the `x-brain-key` header (lowercase, with the dash) or the `?key=` query parameter. It does not accept `Authorization: Bearer`.

So do not reach for `hermes mcp add open_brain --url ... --auth header`: that path always writes `Authorization: Bearer ${MCP_OPEN_BRAIN_API_KEY}` and the result is an auth rejection that looks like a wrong key. Set the header directly — recipe in the `hermes-agent` skill, `references/native-mcp.md` → "Custom auth headers (non-Bearer)".

## Hermes side

```bash
hermes config set mcp_servers.open_brain.url 'https://<ref>.supabase.co/functions/v1/open-brain-mcp'
hermes config set mcp_servers.open_brain.headers.x-brain-key '${OB_MCP_KEY}'   # single-quote the ${...}
```

Then add to `$HERMES_HOME/.env` (`hermes config env-path` prints the path):

    OB_MCP_KEY=<the MCP access key>

For a user with no shell, do not let them hunt for the file: the dashboard's **Files** tab deliberately never lists `.env`. Have them use **Config → Keys → Custom Keys → Add a custom key** with variable name `OB_MCP_KEY` — it appends the line for them, and the value stays write-only in the UI. Never ask him to paste the key into the chat; hand him the place to put it and let him do it.

Verify, then reload the session:

```bash
hermes mcp test open_brain
```

Expect **4** tools: `search_thoughts`, `list_thoughts`, `thought_stats`, `capture_thought`. Current OB1 `main` also registers a read-only `search`/`fetch` pair for ChatGPT compatibility, so a server deployed before that commit — Poorna's, verified 2026-11-24 — shows only the four. The four are what Hermes and Claude Code need; the pair matters only if he connects ChatGPT, and getting it means redeploying the function from current `main`.

A cold Edge Function took ~12s to answer the first `hermes mcp test`. Give it a generous timeout rather than reading a slow connect as a failure. `/reload-mcp` in the chat picks it up; a fresh session also works.

If the connect itself fails, in order: `skip_preflight: true` (OB1 answers a bare `GET` with JSON, which can trip the startup content-type probe), then `protocol: legacy` if it objects to the protocol era. Both are keys on `mcp_servers.open_brain`.

## Supabase side prerequisites

The MCP server is not "a Supabase project" — it is a function deployed onto one. Supabase → Edge Functions must show `open-brain-mcp` as ACTIVE. If it does not, OB1's `docs/01-getting-started.md` is the authority; the steps that get skipped and cost the most time:

1. pgvector extension ON, then the SQL: `thoughts` table + indexes, `match_thoughts()`, `upsert_thought()` (content-fingerprint dedup), the RLS policy, and `grant select, insert, update, delete on table public.thoughts to service_role`. New Supabase projects no longer grant CRUD to `service_role` by default, so without that grant every capture and search returns "permission denied for table thoughts" — 401-shaped noise that is not an auth problem.
2. Supabase secrets: `MCP_ACCESS_KEY` (this is the value Hermes stores as `OB_MCP_KEY`) and `OPENROUTER_API_KEY` (embeddings at 1536 dimensions plus metadata extraction both route through OpenRouter).
3. `supabase functions deploy open-brain-mcp --no-verify-jwt`. The `--no-verify-jwt` matters: OB1 does its own key check and the Supabase JWT gate would reject the client first.

## The other functions on the same project

The same Supabase project also hosts `open-brain-rest` (the ingest/read layer the Discord bot and the Claude Code ambient hook post through) and `agent-memory-api`. What each exposes, and the procedure for auditing the store through them, is in `references/open-brain-audit.md`.

## Adding a function to the project

Only needed for a client that cannot reach REST — Hermes already updates and deletes through `open-brain-rest` (see `references/open-brain-audit.md`). Do not build this to solve a Hermes-side gap.

1. Stage the upstream file **verbatim**, never edited: `integrations/<name>/{index.ts,deno.json}` → `supabase/functions/<slug>/`, then `sha256sum` the copy against the integration source so "unmodified upstream" stays a checkable claim.
2. Type-check before deploying: `cd supabase/functions/<slug> && deno check index.ts`, with `DENO_DIR` pointed off the home directory. The official installer requires `unzip` or `7z`; where neither exists, download `https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip` and extract it with Python's `zipfile`, then `chmod +x`.
3. Smoke-test locally first: `scripts/smoke_test_mcp_function.sh <function-dir>` runs the function on dummy Supabase credentials and asserts the guards — `GET` → 405, `POST` with no key or a wrong key → 401, then an MCP `initialize` + `tools/list` that must return the tool schema. No store access and no credentials needed.
4. Deploy: `supabase functions deploy <slug> --project-ref <ref> --no-verify-jwt`. `--project-ref` with `SUPABASE_ACCESS_TOKEN` needs no `supabase link` and no database password. `MCP_ACCESS_KEY` and `OPENROUTER_API_KEY` are project-level secrets, so a newly added function inherits them and needs none set of its own.
5. Register it in Hermes with the custom-header recipe above under a name distinct from `open_brain` (`open_brain_update`, `open_brain_delete`), then `hermes mcp test <name>`.

Hermes holds no Supabase CLI or token, so this path needs either his credentials or him running the commands. `/opt/data/projects/OB1/deploy-ob-admin-functions.sh` covers steps 2–4 for the two staged write functions.

## Hermes memory provider (`integrations/hermes-agent-memory`)

A native Hermes `MemoryProvider` (name `ob1`) over `agent-memory-api`. Stdlib-only Python, no pip.

1. **Backend first.** `GET <ref>/functions/v1/agent-memory-api/health` → `ok:true` proves only the function. Prove the schema with a real `POST /recall` (`schema_version: openbrain.agent_memory.recall.v1`, `workspace_id`, `query`, `runtime: {name, version}` — no extra keys in `runtime`) returning `recall_response.v1`, plus a wrong-key call → 401.
2. **Install** from the local clone: copy `plugin/__init__.py` and `plugin/plugin.yaml` to `$HERMES_HOME/plugins/ob1/`.
3. **Config:** `$HERMES_HOME/ob1.json` with `endpoint` = the full `.../functions/v1/agent-memory-api` URL (the README's `localhost:8000` is a placeholder), `workspace_id`, `auto_recall`, `auto_capture`, `require_review_by_default: true`. The plugin reads its key from `OPENBRAIN_KEY`, which is the same value as `OB_MCP_KEY`. Back up `.env`, then append `OPENBRAIN_KEY` from the existing value in a shell, so the key never passes through chat or output.
4. **Activate:** `hermes config set memory.provider ob1`. Verify with `hermes memory status` (expect installed ✓, available ✓, `← active`).
5. **End-to-end:** run one `hermes -z "<test turn>"`, then `GET /memories?workspace_id=<ws>`. Check `provenance.runtime == hermes` and `provenance.model`. The list response nests runtime and model under `provenance`; there are no top-level columns. Then clean up the test rows (removal procedure in SKILL.md → "Agent Memory").

**Route mismatch in the shipped plugin.** The plugin's list-memories and review-queue tools send `POST /memories/list` and `POST /memories/review`. The API serves `GET /memories?workspace_id=…` and `GET /memories/review?workspace_id=…`, so both tools 404. Recall, writeback, usage, `PATCH /memories/:id/review` and recall traces match. Before patching, re-check upstream, since it may have been fixed since. Patch the installed copy in `$HERMES_HOME/plugins/ob1/`, never the clone. Note that a future copy-over from upstream overwrites the patch.

**Turning down noise:** `auto_capture: false` in `ob1.json` stops the per-turn writeback while keeping auto-recall and the explicit `ob1_*` tools. Offer it when turn summaries mixing into his normal OB search would bother him.

**Check route parity on any third-party OB1 client.** Grep the client for `_request("VERB", "/path"` and the server for `app.(get|post|patch)(` and compare the two lists before trusting the README. An approved community contribution can ship calls the API never served.

## Rotation

`MCP_ACCESS_KEY` is one key shared by the core server and every OB1 extension, so rotating it breaks all of them at once. Change it deliberately and update `OB_MCP_KEY` in `.env` in the same pass.
