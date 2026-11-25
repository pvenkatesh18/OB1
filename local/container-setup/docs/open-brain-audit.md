# Auditing the Open Brain store

Use when he asks to review, verify, inventory, or reconcile the store against his setup — or before proposing new OB functionality.

Ground truth: the **live surfaces** for what the store currently does, and the **repo clone at `/opt/data/projects/OB1`** (shallow, `main`) for what a surface is capable of. Read `schemas/` and `integrations/` there instead of inferring capability from behaviour — the MCP surface showing four tools does not mean the project lacks an update route.

## Which surface to use

| Need | Surface |
| ---- | ------- |
| Topic / person / idea lookup, totals, writes | MCP (`mcp_open_brain_*`) |
| Whole-store inventory, per-row fields, which capture channels are live, update / delete / duplicates | `open-brain-rest` |
| Whether agent-memory sidecars have anything in them | `agent-memory-api` |

`list_thoughts` returns each thought's full untruncated content. Ambient session transcripts are ~40 KB apiece, so enumerating the store over MCP is hundreds of KB and will spill or flood the context. Never do it — page the REST endpoint to disk instead.

A **bounded slice** is the exception: `list_thoughts type=task` ("what's pending"), or one topic/person search. The row count is small but the payload is not — task rows include whole session transcripts — so expect the saved-output path and parse from it (SKILL.md → "what were my pending items").

## Snapshot before you report or propose anything

Page the whole store to a workspace file in one pass, and keep it for the rest of the session. Other writers are live (the Mac's Discord bot, the Claude Code Stop hook, manual dashboard edits), so rows can appear or vanish between two reads — a later re-read is a *different* store, not a corrected one. That snapshot is also the only copy of a row that someone deletes mid-session, so recovering a destroyed row from it is a real use, not a theoretical one. When the row count moves, diff the id sets and name the rows that appeared or disappeared rather than reporting a bare number change.

## Inventory procedure

1. Read the key inside Python with a regex (`^OB_MCP_KEY\s*=\s*(.+)$` on `$HERMES_HOME/.env`), not with `cut`/`tr` shell gymnastics — the value's characters break quoting and you get an empty key that surfaces as a confusing JSON `KeyError` rather than an auth error. Never print the key.
2. `GET {base}/open-brain-rest/thoughts?per_page=50&page=N` with header `x-brain-key: <key>`. This route pages on `per_page`/`page` and **ignores `limit`**; `per_page` defaults to 25. Loop `page` until the accumulated rows reach `total`, and treat a response with no `data` key as an error, not an empty store.
3. Save each page to the workspace and aggregate in Python: `Counter` over `source_type`, `type`, `status`, `importance`; group rows by their embedded session header. Do not eyeball a listing — every total you state must come from the parsed rows.
4. Every row carries `content`, `created_at`, `type`, `source_type`, `status`, `importance`, `quality_score`, `sensitivity_tier`, and `metadata` with `type`, `topics`, `people`, `action_items`, `dates_mentioned`, `source`. These per-row fields exist only on this surface; the MCP tools hide them.

## The `type` column is not what the listing shows

`/thoughts` normalizes each row with a `metadata.type` fallback, so a row whose `type` **column** is NULL still displays a type. `/stats` calls the `brain_stats_aggregate` RPC, which maps that NULL to `unknown` — that is the whole mechanism behind the two surfaces disagreeing (and behind the MCP stats folding those rows into observations).

Effect: `?type=<t>` filters the **column**, so it silently undercounts — an `?type=observation` query returning 8 against 15 observations is this, not missing rows. Fix and detect it with `scripts/ob_admin.py repair-types [--dry-run]`, which fills each NULL from `metadata.type`.

Do **not** detect the NULLs by fetching `?type=<t>` for a fixed list of canonical types and subtracting: `type` is free text, so that flags every off-list row as NULL (a bare `decision` was observed on a fresh capture) and re-writes rows that were already correct. Group the rows by the value the listing reports and ask the column for each of those values once — anything the column does not return is genuinely NULL. That is what `repair-types` does.

`type` is free text, not an enum — the classifier can emit values outside the documented set (a bare `decision` was observed on a fresh capture). Filter on the values you know and then look for stragglers rather than assuming a closed set. Don't assume the writer is at fault either: `/capture` was once measured as leaving the column NULL and then failed to reproduce, so trust a fresh measurement over an earlier one.

## Checks worth running

- **`source_type` mix** — which capture channels are actually writing (`mcp` = him or an agent through the MCP tool, `discord_capture` = the Discord bot, `claude_code_ambient` = the Claude Code Stop hook). This is how you confirm a capture integration is real rather than a stub, without being able to read any of their code.
- **Re-captured sessions** — for content starting `Claude Code Session Transcript`, parse the embedded `Date: <session ts>`, `Project: <name>` and `Turns: N`. Rows sharing one session timestamp are the SAME session captured repeatedly: the Stop hook fires on every assistant stop, not once at session end, and each snapshot is a superset of the last so content-fingerprint dedup can never catch it. Exact-hash duplicate checks come back clean and miss the whole problem. To establish the chain:
  - Group by the session `Date` **alone**. Never group by (Date, project): the `Project:` label can change between snapshots of one session, which splits one chain into two — and that is also why `/duplicates` under-reports these.
  - Sort each group by `Turns`, then `created_at`, and compare consecutive pairs as **line sets taken below `<thought_content>`**. If the earlier set is a subset, the later snapshot carries everything.
  - Never test containment as a substring/`in` check on the whole content: the `Turns: N` header line differs between snapshots, so every pair reports as *not* contained and you will wrongly conclude the snapshots are independent.
  - Only once every pair checks out, keep the last snapshot of the session and delete the earlier ones — and re-run the subset check **immediately before each delete**, not from the earlier analysis, because other writers are live and he may be cleaning up in parallel. Treat `/duplicates` as a second opinion, not the enumeration: at its 0.85 default it can miss a link in a chain it should have paired.
  - The cause stays: this grows back until the hook is changed on his Mac (capture once per session, as a summary rather than the raw transcript, or upsert on a session id).
- **Stat disagreement** — see the `type`-column section above before calling it corruption.
- **Classifier tells** — one- or two-word captures come back with empty `topics` (expected, not a broken classifier), and 30-character rows are usually too short to classify at all.
- **Same fact captured twice** — watch for a duplicated pair where a number or unit drifted between them (a mangled figure next to the good one). Both stay and a semantic search returns either, so flag it as a correctness risk. If the good copy is the one that gets deleted, the surviving mangled row needs a content *update*, and your earlier snapshot is where the correct text can be recovered from.
- **Junk rows** — placeholder captures from integration smoke tests and vague one-liners pollute later retrieval. Surface them as a list; nothing in the UI removes them.

## Improvement review ("how can I make OB better?")

Run the snapshot, then check these alongside the ones above. Each finding comes from the parsed rows:

- **`sensitivity_tier` coverage**: OB1's consumers (weekly-digest, `find_derivatives`) always exclude `restricted` and skip `personal` by default, so a store where every row is `standard` has no privacy gate, even with finance/medical/family rows in it. Fix with `ob_admin.py update --sensitivity-tier`, which is cheap and reversible. Do this before any digest or derived-artifact recipe goes on top.
- **Capture cadence**: count rows per month by `source_type`. If manual (`mcp`/`discord_capture`) captures stop while only the ambient hook keeps writing, the store is giving nothing back. Propose a read-back loop (a digest) rather than more capture channels.
- **Bytes per source, not just rows**: sum `len(content)` by `source_type`. Raw ambient transcripts can be a small share of rows but most of the bytes, and the classifier types them badly (a finance session filed as `task`). Name that share when you recommend changing the hook.
- **Stale open tasks**: count `type=task` rows not `done` by age. Scan their text for security actions (leaked tokens and similar) and raise those first.
- **Junk / expired rows**: smoke-test captures, one-liners with no context, and facts with an expiry date that has already passed.
- **Importance never scored**: if `importance` only ever shows the writer defaults, ranking-based recipes have nothing to rank on.

Deliver it as a short findings table plus a ranked list. Give each item what he gains and what it risks, end with numbered questions he can answer tersely, and keep anything needing a Mac-side or Supabase-CLI change clearly separate from what Hermes can do itself.

## Checking whether a recipe is installed

Recipes live in `/opt/data/projects/OB1/recipes/<name>/`. Their README lists the layers and the schema each depends on. Check each layer on its own:

| Layer | Evidence |
| ----- | -------- |
| Schema (`schemas/<name>`) | Hermes has no DB access, and REST `/thoughts` returns a fixed field set (it does not expose extra columns like `derived_from`), so missing fields there prove nothing. Look for a prior schema audit stored in OB: earlier Claude Code sessions on the OB1 project audited applied schemas. Search the snapshot for the schema name and quote the verdict with its date, labelled as not re-verified. |
| MCP tools the recipe registers | `hermes mcp test open_brain` lists the deployed tools, which is conclusive. |
| Backfill / eval scripts | Look for the metadata keys the script writes (e.g. `metadata.provenance`, `eval_score`) across all rows. No row carrying them = not run. |
| His intent | An `idea`/`task` row naming the recipe, and its `status`. |

Check the recipe's precondition too. A recipe that only acts on derived artifacts (digests, wikis) does nothing on a store that has none, so say "not worth finishing yet" and name what has to come first.

## Probing a route that may not exist

Send it a syntactically valid UUID that cannot be a row, and read the **error shape**, not just the status:

- a Supabase error body (`Cannot coerce the result to a single JSON object`) with 404 = the route exists, the row does not;
- a bare `Not Found` = no such route.

Never probe `DELETE` with a real id, and never trust a delete's success: `DELETE /thought/:id` answers `{"action":"deleted"}` with 200 even for an id that was never there. Verify with a follow-up `GET`, which is what `ob_admin.py` does — it pre-flights, refuses an id that does not resolve, prints the target, and needs `--yes`.

An existing route set answers "can this be done at all", so check the deployed surface's routes before concluding a capability needs a new deploy.

## Quirks that look like bugs and are not

- **You cannot read an Edge Function's source or env.** Infer deployed behaviour from the data it produced: a `source_type` tag surviving ingestion proves the `/ingest` handler honours `body.source_type`; a rewording or a new field proves nothing. Say "unverifiable from here" for anything the data does not answer — e.g. which model the metadata classifier runs, which no key on this machine can reveal, and note that a plan recorded in a stored thought is not evidence it was executed.
- **The Vercel dashboard 302s to `vercel.com/sso-api`** while Vercel Deployment Protection is on, so treat it as unavailable for verification and say so rather than presenting it as the fix for a UI gap. Turning that protection off is his call, not yours.
- **`agent-memory-api` needs `?workspace_id=`** (his default workspace is `ob1-staging`); an empty list is the expected state until an agent runtime writes memories, so "deployed" and "in use" are different claims.
- **His captures are mixed personal/work** — household, family, medical and financial rows sit beside work ones. Anything OB-derived headed for work-facing output needs those layers stripped first.
- **Two writers, two defaults** — `POST /capture` assigns `importance` 50 / `quality_score` 70 while the MCP-and-ingest path leaves the schema defaults (3 / 50). A bimodal `importance` is that, not corruption.

## Known gaps in this instance

- The **MCP** surface is capture+read only, which reads as "nothing can be corrected" — but the REST function on the same project also exposes `PUT`/`DELETE`/`/duplicates`/`/search`. For Hermes that gap is closed by `scripts/ob_admin.py`. Other clients (Claude Desktop/Code, ChatGPT) still have no write path until the staged `update-thought-mcp` / `delete-thought-mcp` are deployed — see `references/open-brain-setup.md`.
- `thought_audit` is unbuilt and has no writer, so a delete leaves no in-store record, and the delete route is a hard delete with no undo. Poorna declined both a tombstone and the audit schema on 2026-11-24 and told Hermes not to change how delete works — leave it and don't re-propose it.
- A server deployed from an older `main` also lacks the read-only `search`/`fetch` pair, which is only needed for a ChatGPT connection (see `references/open-brain-setup.md`).
- Schema state from the last stored audit (Claude Code OB1 session; Hermes cannot re-verify): applied = `agent-memory`, `enhanced-thoughts`, `provenance-chains`, `workflow-status`; not applied = `thought-audit`, `smart-ingest`, and the rest. The provenance-chains recipe stops at the schema: its MCP tools (`trace_provenance`, `find_derivatives`, `capture_derived_thought`) are not deployed and no backfill has run. Its SQL helpers are SECURITY DEFINER and granted to `anon`, so the restricted-row redaction they do is the only protection, and it means nothing until rows are actually tiered.
- Repeated session captures are the store's dominant content by volume, and any cleanup regrows until the hook changes on his Mac.
