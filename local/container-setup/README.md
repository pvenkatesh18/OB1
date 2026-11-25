# OB — Poorna's Open Brain container setup

Personal, working changes to Poorna's Open Brain (OB1) deployment, captured from the
container on 2026-11-25. This is **not** upstream code; it is the delta between
NateBJones-Projects/OB1 `main` and what is actually running in this container.

Branch: `local/container-setup` off this fork's `main`. Nothing here is proposed
upstream unless stated.

## Branch layout

- The two real code changes are applied at their **real upstream paths** at the root
  of this branch — `git diff main` shows exactly the fix, nothing else.
- Everything else (tooling, docs, config, evidence, and the same two changes again as
  `.patch` files) lives under `local/container-setup/`. It is kept out of the repo
  root so this branch does not touch OB1's own `README.md` or `.gitignore`.

Upstream repo (read-only reference for what a surface *can* do):
`/opt/data/projects/OB1` @ `238df6c`
Project ref: `byawvafeuychywyigxsn`

---

## What is in here

### `patches/` — the two real code changes

| Patch | Applies to | What it fixes |
|---|---|---|
| `plugin-http-endpoints-fix.patch` | `integrations/hermes-agent-memory/plugin/__init__.py` | Upstream sends `POST /memories/list` and `POST /memories/review`; the deployed Agent Memory API exposes these as **GET** with query-string filters. The POSTs 404, so `list_memories` and `get_review_queue` were dead. Adds `import urllib.parse` and `urlencode`s the workspace id. |
| `consolidation-metadata-pr435-plus-guard.patch` | `integrations/consolidation-workers/metadata-norm/index.ts` | Deployed variant. Base = upstream `@ 238df6c`, plus upstream PR #435 (NULL-safe candidate selection, low-confidence skips marked reviewed, classifier prompt calibration, opt-in `EXCLUDE_DERIVED_THOUGHTS`) **plus two local hardening changes**: (a) a numeric confidence guard, because `metadata->>confidence.lt.0.7` is a *text* comparison on the PostgREST side; (b) an unnormalized-importance arm (`importance > 6`) so rows written with out-of-range importance (observed: `50`) still get normalized. |

Both were verified to `git apply --check` cleanly against `/opt/data/projects/OB1` @ `238df6c`.

### `patches/` and the applied files

The two `.patch` files here are the same two changes already applied at their real
paths at the root of this branch, kept as standalone patches so they can be lifted
into another checkout without merging this branch.

### `scripts/` — local tooling (not upstream)

| File | What it does |
|---|---|
| `deploy-ob-admin-functions.sh` | Deploys `update-thought-mcp` and `delete-thought-mcp` to the Supabase project. **Not needed for Hermes** — the already-deployed `open-brain-rest` function already has `PUT`/`DELETE /thought/:id`. Only for MCP-only clients (Claude Desktop, Claude Code, ChatGPT, Codex). |
| `ob_admin.py` | CLI over the already-deployed `open-brain-rest` routes. The 4-tool MCP server has no write path; this does `update` / `delete` / `repair-types` / `duplicates` / `search`. Reads `OB_MCP_KEY` from `.env` and never prints it. |
| `smoke_test_mcp_function.sh` | Runs a staged edge function on **dummy** credentials locally — checks the method guard (405), key guard (401), then the MCP initialize handshake and `tools/list`. Use before deploying. |

### `docs/` — OB setup and audit notes

`personal-knowledge-capture.SKILL.md` is the Hermes skill that drives all of this
(with `docs/open-brain-setup.md` and `docs/open-brain-audit.md` as its references).
Kept here because they document routes, traps and checks that are otherwise only in
the container.

### `config/ob1.json`

Plugin config: endpoint, `workspace_id: default`, auto-recall/capture flags.
**No secrets** — the auth key (`OB_MCP_KEY` / `OPENBRAIN_KEY`) lives in `.env` and is
deliberately not reproduced here.

### `evidence/`

`dryrun-limit20.json` — dry-run output of the consolidation-metadata worker
(20 candidates, 18 changes, 0 errors) that justified the deployed variant.

---

## Deliberately excluded

- `supabase/functions/{update,delete}-thought-mcp/**` — upstream's `.gitignore` has
  `supabase/`, so deploy staging is out of git **by design**.
- `.env`, `config.yaml`, `google_token.json`, any key material — credentials.
- `deploy-ob-admin-functions.sh`'s staged function copies: byte-identical to upstream
  `integrations/{update,delete}-thought-mcp/index.ts`.
