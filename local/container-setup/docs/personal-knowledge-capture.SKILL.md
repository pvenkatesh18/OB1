---
name: personal-knowledge-capture
description: Use for 'Capture.', OB setup/audits, reminders, calendars.
---

# Personal knowledge & schedule (Poorna)

## Open Brain — what it is, and whether it is wired
- "Open Brain" / "OB" / "PV Open Brain" = Nate B. Jones's OB1 (github.com/NateBJones-Projects/OB1): a personal thought store behind a Supabase Edge Function that speaks MCP. It is not a Hermes feature and not the Supabase connector.
- Wire it under the Hermes server name `open_brain`, so its tools appear as `mcp_open_brain_capture_thought`, `mcp_open_brain_list_thoughts`, `mcp_open_brain_search_thoughts`, `mcp_open_brain_thought_stats` — four tools, all confirmed live on 2026-11-24. (Current OB1 `main` also registers a read-only `search`/`fetch` pair for ChatGPT compatibility; a server deployed before that commit, like his, exposes only the four.)
- **Confirm it is registered before reporting you cannot capture:** `hermes mcp test open_brain` (exit 0 = connected and tools discovered, 3 = not in this profile's config) or `hermes mcp list`. A tool named in this skill is not evidence the server exists.
- Wiring, repair, and the auth trap: `references/open-brain-setup.md`.

## "Capture. <text>"
- Call `mcp_open_brain_capture_thought` with the text as given (no rewriting). Reply with a one-line confirmation.
- If the call fails on auth, say so plainly instead of retrying silently, and point at `references/open-brain-setup.md`.

## "check reminders" / "ACT Now items on OB" / "what were my pending items"
- Reach **his** rows through the OB MCP tools, not the `ob1_*` agent-memory recall: `ob1_recall`/`ob1_search` return Hermes turn summaries (`source.kind = agent_memory`) that outrank his own captures and will answer a question he asked about his own notes with yesterday's agent chatter. Recall gives session context; the MCP tools give his store. Say which surface an answer came from.
- Enumerate with `mcp_open_brain_list_thoughts` `type=task` (newest first, limit 20–30), optionally narrowed with `days=`. Do **not** lead with a semantic `search_thoughts` query: paraphrasing his own wording can return "No thoughts found" while the rows are sitting there, so an empty semantic search is a statement about the phrasing, not about the store. Search semantically to confirm one row once you know what you are looking for.
- That listing returns each row's **full** content (session transcripts run tens of KB), so a large result arrives as a saved-output path plus a preview instead of inline text. Parse that saved file in Python — split on the entry boundary `^\d+\. \[\d{1,2}/\d{1,2}/\d{4}\] \(type( - tags)?\)`, then print the first line and a short body snippet per entry — rather than re-requesting the listing or paging it through a line-numbered reader (the saved file carries no line prefixes).
- Answer newest first, older items one line each, and never call an item open or closed from its own text: check live state (an item asking for a `person_note` with his name and pronouns is open exactly when `list_thoughts type=person_note` holds no such row), and run `cronjob_manage action=list` whenever a reminder is involved so you can say whether it is actually scheduled and when it next fires.
- Reminder times are read as **UTC** — convert his ET wall-clock times before scheduling (9 PM ET = 02:00 UTC the next day); an ISO time is taken as UTC and a `timezone` field is ignored, so an unconverted late-evening ET time is rejected as "in the past" or fires hours off. Confirm the stored time from `cronjob_manage action=list`, whose `next_run_at` prints its offset.
- To close, retype, or remove one, use `scripts/ob_admin.py` (see "Correcting and removing entries" below).

## Auditing the store ("does OB match my setup?")
- Inventory from the **REST function, never by enumerating `mcp_open_brain_list_thoughts`**: it returns each thought's FULL untruncated content, and ambient session transcripts run ~40 KB each, so a whole-store listing is hundreds of KB and floods the context. MCP = topic search, counts, writing. REST = the inventory.
- The upstream repo is cloned at `/opt/data/projects/OB1` (shallow, `main`). Read its `schemas/` and `integrations/` when you need to know what a surface *can* do — deployed behaviour only tells you what it currently does. Procedure, row fields, route probing and the checks worth running: `references/open-brain-audit.md`.
- You cannot read an Edge Function's source or its secrets. Verify a deployed change from the data it produced (e.g. `source_type` tags surviving ingestion prove `/ingest` honours `source_type`) and label everything else unverifiable rather than guessing.
- **"Is recipe/schema X installed?"** — an OB1 recipe is layered (schema SQL → MCP tool blocks pasted into the server → one-time/scheduled scripts), and each layer is installed separately. Answer per layer with the evidence for each, never one yes/no. Procedure in `references/open-brain-audit.md` → "Checking whether a recipe is installed".
- **"How can I make OB better?"** — snapshot first, then rank by impact the checks under "Improvement review" in `references/open-brain-audit.md`. Recommend a recipe only once the thing it works on exists in the store.
- `mcp_open_brain_thought_stats` and the REST `/stats` bucket types differently and will disagree over the same store: the gap is rows whose `type` **column** is NULL, which the `/thoughts` listing hides behind a `metadata.type` fallback (detection and fix in `references/open-brain-audit.md`). Quote a number with the surface it came from, and don't report the gap as data corruption.

## Correcting and removing entries (the MCP server cannot)
- The 4-tool MCP server has no write path, but the **already-deployed** REST function on the same project does: `PUT /thought/:id`, `DELETE /thought/:id`, `GET /duplicates`, `GET /thought/:id/connections`, `POST /search` (semantic or text). No deploy needed for Hermes — `scripts/ob_admin.py` is the CLI over those routes. It reads `OB_MCP_KEY` from `.env` and never prints the key.
  - reads: `stats`, `list [--type|--source-type|--status]`, `get --id`, `search --query [--mode semantic|text]`, `duplicates`
  - `update --id U [--content TEXT] [--metadata-patch '{"k":v}'] [--type T] [--status S] [--importance N] [--quality-score N] [--sensitivity-tier T]`
  - `repair-types [--dry-run]` — fills the `type` column on rows where it is NULL, from `metadata.type`. Detection is value-agnostic; never test `type` against a fixed list of values.
  - `delete --id U --yes`
- **`--metadata-patch` cannot change the top-level `type` column** (it shallow-merges into the `metadata` JSONB only), so `metadata.type` and `type` drift apart. Use `--type` for that, and note `update` verifies a `--type` change through the `?type=` filter rather than the before/after listing diff, which cannot see the column.
- Delete is a **hard** delete — no undo, no trash, and the deployed route writes no audit row. Poorna's explicit instruction (2026-11-24): **do not change how delete works, and no tombstones.** Leave the path as it is — pre-flight GET, print the target, require `--yes`, then read back — and don't re-propose a tombstone or audit layer for it. OB1's own `deleting-thoughts` rule still applies as judgement, not machinery: prefer updating or tagging (`--metadata-patch '{"superseded": true}'`) over removing, and delete only a test row, an exact duplicate, or an accidental capture.
- `schemas/thought-audit` (local clone: `/opt/data/projects/OB1/schemas/thought-audit/schema.sql`) is **storage only** — no trigger, and none of the three writers inserts a row. Running that SQL alone buys a permanently empty table; it is only worth applying alongside a deployed function carrying the audit insert. Don't offer it as the fix for recoverability — there is no recovery path, and he wants it that way.
- Resolve the id with `list`/`search` **in the same session**; never delete an id recalled from earlier context. `ob_admin.py delete` refuses an id that doesn't resolve, prints the target, and does nothing without `--yes` — run it once bare, read the target, then confirm.
- `update` reads the row back and prints exactly which fields changed (`verified: …`). Report that line; never answer "done" from the 200 alone.
- Other writers hit this store (the Mac's Discord bot, the Claude Code ambient hook, manual dashboard edits), and `PUT` is last-write-wins unless the caller passes `if_unchanged_since`. Rows can appear or vanish between two reads — re-read rather than trusting an earlier listing, and judge currency by `updated_at`, not `created_at`.
- `delete-thought-mcp` **is deployed** on his project (single tool `delete_thought`, hard delete, `x-brain-key` auth, JSON-RPC `tools/call` over POST with `accept: application/json, text/event-stream`). It answers "Thought not found" for an unknown id — send one fake id alongside real deletes as the negative control. Probe a function's existence with an MCP `tools/list` POST rather than trusting this skill's inventory. `update-thought-mcp` is staged at `/opt/data/projects/OB1/supabase/functions/`; deploy with `/opt/data/projects/OB1/deploy-ob-admin-functions.sh` only if a *non-Hermes* client needs it. Smoke-test any such function locally first with `scripts/smoke_test_mcp_function.sh <function-dir>` (method and key guards plus tool registration, no store access); the staging, type-check and deploy recipe is in `references/open-brain-setup.md`. All of it needs Supabase CLI access, which Hermes does not hold.

## Agent Memory (the `ob1` Hermes memory provider)
- When the `ob1` memory provider is active (`hermes memory status`), Hermes auto-recalls from and auto-writes to `agent-memory-api` on every meaningful turn. Install, config files, verification and the known client/API route mismatch: `references/open-brain-setup.md` → "Hermes memory provider".
- **Every agent memory is also a row in `thoughts`**, so the standard OB MCP search/list/stats see it as an ordinary captured thought, even after it is rejected. To remove an agent memory fully: `PATCH /memories/:id/review` with `action: reject` (no delete route exists), then hard-delete its `thought_id` via `delete_thought`, then confirm with an MCP `search_thoughts` that it is gone. A reject alone leaves it visible in his normal searches.
- One test turn writes several memories (the turn summary, any explicit `ob1_writeback` the agent made, and session-end findings). List by workspace after a test and remove all of them, not just the one you expected.
- Before patching the plugin or API, check upstream first (`git fetch` the clone and diff the files, then GitHub issues/PRs search via the API). Report what upstream says before proposing the local patch.

## Household facts
- Household/family details stay out of work-facing output.

## Schedule questions
- List all calendars, query each one, including Family — never just primary.
- When a request names two appointments, keep them separate; check the calendar before assuming something isn't already booked.
