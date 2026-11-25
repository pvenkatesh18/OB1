#!/usr/bin/env python3
"""ob_admin.py — update / delete / inspect thoughts in Open Brain (Poorna's instance).

Talks to the ALREADY-DEPLOYED `open-brain-rest` Supabase Edge Function.
No deploy, no new credentials: it reuses OB_MCP_KEY from .env (the same key the
MCP server uses, sent as the `x-brain-key` header).

Why this exists: the open-brain MCP server exposes only capture/search/list/stats.
The REST function that is already deployed also has PUT /thought/:id,
DELETE /thought/:id and GET /duplicates — this script is the thin CLI over them
so the agent can actually correct and remove entries.

Usage
  ob_admin.py stats
  ob_admin.py list [--limit N] [--page N] [--type T] [--source-type S] [--status a,b]
  ob_admin.py get --id UUID
  ob_admin.py search --query "..." [--mode semantic|text]
  ob_admin.py duplicates [--limit N] [--offset N]
  ob_admin.py capture --content "..." [--source-type manual]
  ob_admin.py update --id UUID [--content TEXT] [--metadata-patch '{"a":1}']
                      [--type T] [--status S] [--importance N] [--quality-score N]
                      [--sensitivity-tier T]
  ob_admin.py delete --id UUID --yes

Safety
  * delete refuses without --yes and refuses an id that does not resolve.
    It prints the entry first, so a wrong id is caught before it is destroyed.
  * update reads the row back after writing and reports exactly what changed.
  * The access key is never printed.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "https://byawvafeuychywyigxsn.supabase.co/functions/v1/open-brain-rest"
ENV_PATH = os.environ.get("OB_ENV_PATH", os.path.join(os.environ.get("HERMES_HOME", "/opt/data"), ".env"))


def load_key() -> str:
    key = os.environ.get("OB_MCP_KEY")
    if key:
        return key
    try:
        with open(ENV_PATH, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"^OB_MCP_KEY\s*=\s*(.+?)\s*$", line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    sys.exit(f"ob_admin: OB_MCP_KEY not found in environment or {ENV_PATH}")


def call(method: str, path: str, payload=None):
    """Return (status, parsed_body). Never raises on HTTP error status."""
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-brain-key", load_key())
    if data:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode(), e.code
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, {"raw": body[:500]}


def preview(row, width=140) -> str:
    text = re.sub(r"\s+", " ", row.get("content") or "").strip()
    return text[:width] + ("…" if len(text) > width else "")


def short(text, width=140) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:width] + ("…" if len(text) > width else "")


def cmd_stats(a):
    s, b = call("GET", "/stats")
    if s != 200:
        sys.exit(f"ob_admin: stats failed [{s}] {b}")
    print(json.dumps(b, indent=2))


def cmd_list(a):
    # The REST list endpoint takes `per_page` (default 25), not `limit`.
    q = f"/thoughts?per_page={a.limit}&page={a.page}"
    if a.type:
        q += f"&type={a.type}"
    if a.source_type:
        q += f"&source_type={a.source_type}"
    if a.status:
        q += f"&status={a.status}"
    s, b = call("GET", q)
    if s != 200:
        sys.exit(f"ob_admin: list failed [{s}] {b}")
    print(f"total={b.get('total')} page={b.get('page')} per_page={b.get('per_page')}")
    for r in b.get("data", []):
        print(f"{r['id']}  {r['created_at'][:19]}  {r.get('source_type',''):<19} {str(r.get('type')):<11} {len(r.get('content') or ''):>6}  {preview(r)}")


def cmd_get(a):
    s, b = call("GET", f"/thought/{a.id}")
    print(json.dumps(b, indent=2) if s == 200 else f"ob_admin: get failed [{s}] {b}")
    return 0 if s == 200 else 1


def cmd_search(a):
    s, b = call("POST", "/search", {"query": a.query, "mode": a.mode, "limit": a.limit})
    if s != 200:
        sys.exit(f"ob_admin: search failed [{s}] {b}")
    print(f"mode={b.get('mode')} total={b.get('total')}")
    for r in b.get("results", []):
        sim = r.get("similarity")
        head = f"{r['id']}  {r['created_at'][:19]}  "
        head += f"sim={sim:.3f}  " if isinstance(sim, (int, float)) else ""
        print(head + preview(r))


def cmd_duplicates(a):
    s, b = call("GET", f"/duplicates?limit={a.limit}&offset={a.offset}")
    if s != 200:
        sys.exit(f"ob_admin: duplicates failed [{s}] {b}")
    pairs = b.get("pairs", [])
    print(f"threshold={b.get('threshold')} pairs={len(pairs)}")
    for p in pairs:
        print(f"  {p['similarity']:.3f}  A {p['thought_id_a']}  {short(p.get('content_a'), 70)}")
        print(f"           B {p['thought_id_b']}  {short(p.get('content_b'), 70)}")


def cmd_capture(a):
    s, b = call("POST", "/capture", {"content": a.content, "source_type": a.source_type})
    print(f"[{s}] {json.dumps(b)[:400]}")
    return 0 if s == 200 else 1


def cmd_repair_types(a):
    """Fill the `type` column on rows where it is NULL, from metadata.type.

    Detection is value-agnostic on purpose: the column is not limited to the six
    documented types (the classifier also emits e.g. "decision"), so asking the
    ?type= filter for a fixed list of values would flag every off-list row as NULL.
    Instead, group the rows by the type value the listing reports and ask the column
    for each of those values once; any row the column does not return is genuinely NULL.
    """
    rows = []
    for page in range(1, 10):
        s, b = call("GET", f"/thoughts?per_page=50&page={page}")
        if s != 200:
            sys.exit(f"ob_admin: list failed while scanning [{s}] {b}")
        rows += b["data"]
        if len(rows) >= b["total"]:
            break

    listing_types = sorted({(r.get("type") or "") for r in rows})
    in_column = {}
    for t in listing_types:
        if not t:
            in_column[t] = set()
            continue
        s, b = call("GET", f"/thoughts?per_page=100&type={t}")
        in_column[t] = {r["id"] for r in b["data"]} if s == 200 else set()

    nulls = [r for r in rows if r["id"] not in in_column[(r.get("type") or "")]]
    print(f"scanned {len(rows)} rows; {len(nulls)} have a NULL `type` column"
          f"  (checked {len(listing_types)} distinct type values against the column)")
    if not nulls:
        print("nothing to repair")
        return 0
    off = 0
    for r in sorted(nulls, key=lambda r: r["created_at"]):
        t = (r.get("metadata") or {}).get("type")
        if not t:
            print(f"  SKIP {r['id']} — no metadata.type to copy either")
            continue
        if a.dry_run:
            print(f"  DRY  {r['id']} {r['created_at'][:19]} would set type={t!r}")
            continue
        s, _ = call("PUT", f"/thought/{r['id']}", {"type": t})
        if s == 200:
            off += 1
            print(f"  set  {r['id']} {r['created_at'][:19]} type={t!r}")
        else:
            print(f"  FAIL {r['id']} [{s}]")
    if not a.dry_run:
        print(f"filled {off} of {len(nulls)}")
    return 0


def cmd_update(a):
    payload = {}
    if a.content is not None:
        payload["content"] = a.content
    if a.type is not None:
        payload["type"] = a.type
    if a.status is not None:
        payload["status"] = a.status
    if a.importance is not None:
        payload["importance"] = a.importance
    if a.quality_score is not None:
        payload["quality_score"] = a.quality_score
    if a.sensitivity_tier is not None:
        payload["sensitivity_tier"] = a.sensitivity_tier
    if a.metadata_patch:
        try:
            payload["metadata"] = json.loads(a.metadata_patch)
        except json.JSONDecodeError as e:
            sys.exit(f"ob_admin: --metadata-patch is not valid JSON: {e}")
    if not payload:
        sys.exit("ob_admin: nothing to update — pass --content, --metadata-patch, --type, --status, …")

    s, before = call("GET", f"/thought/{a.id}")
    if s != 200:
        sys.exit(f"ob_admin: refusing to update — id did not resolve [{s}] {before}")
    print(f"before: {preview(before)}")
    print(f"        updated_at={before.get('updated_at')}")

    s, b = call("PUT", f"/thought/{a.id}", payload)
    if s != 200:
        sys.exit(f"ob_admin: update failed [{s}] {b}")

    # Read-back verification: report what the server actually stored.
    s2, after = call("GET", f"/thought/{a.id}")
    if s2 != 200:
        sys.exit(f"ob_admin: update returned 200 but read-back failed [{s2}] {after}")
    print(f"after : {preview(after)}")
    print(f"        updated_at={after.get('updated_at')}")
    changed = []
    if a.content is not None and after.get("content") != before.get("content"):
        changed.append("content (re-embedded)")
    if a.metadata_patch:
        bm, am = before.get("metadata") or {}, after.get("metadata") or {}
        for k in sorted(set(bm) | set(am)):
            if bm.get(k) != am.get(k):
                changed.append(f"metadata.{k}: {json.dumps(bm.get(k))[:60]} -> {json.dumps(am.get(k))[:60]}")
    for f in ("status", "importance", "quality_score", "sensitivity_tier"):
        if before.get(f) != after.get(f):
            changed.append(f"{f}: {before.get(f)!r} -> {after.get(f)!r}")

    # `type` needs a column-level check, not the before/after diff: the /thoughts
    # listing falls back to metadata.type when the `type` COLUMN is NULL, so a
    # column-only fill looks like "no change" even though the column did change.
    # The ?type= filter queries the column itself, so ask it directly, both sides.
    if a.type is not None:
        def in_type_column(t):
            s, c = call("GET", f"/thoughts?per_page=100&type={t}")
            return s == 200 and any(r["id"] == a.id for r in (c.get("data") or []))

        was = bool(before.get("type")) and in_type_column(before["type"])
        now = in_type_column(a.type)
        changed.append(
            f"type column: {'set' if was else 'NULL (the listing masked this via the metadata.type fallback)'}"
            f" -> {a.type!r} [{'set' if now else 'STILL NULL — check the write'}]"
        )
    print("verified: " + ("; ".join(changed) if changed else "no field actually changed"))
    return 0


def cmd_delete(a):
    s, row = call("GET", f"/thought/{a.id}")
    if s != 200:
        sys.exit(f"ob_admin: refusing to delete — id did not resolve [{s}] {row}. "
                 f"(Note: DELETE on this API returns success even for unknown ids.)")
    print("target:")
    print(f"  id         {row['id']}")
    print(f"  created    {row['created_at']}")
    print(f"  source     {row.get('source_type')}  type={row.get('type')}  chars={len(row.get('content') or '')}")
    print(f"  content    {preview(row, 200)}")
    if not a.yes:
        sys.exit("\nob_admin: hard delete, no undo. Re-run with --yes to confirm this exact id.")
    s, b = call("DELETE", f"/thought/{a.id}")
    if s != 200:
        sys.exit(f"ob_admin: delete failed [{s}] {b}")
    s2, _ = call("GET", f"/thought/{a.id}")
    print(f"deleted {row['id']} (prior content length: {len(row.get('content') or '')} chars); "
          f"read-back {'confirms gone' if s2 == 404 else f'unexpected [{s2}]'}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    pl = sub.add_parser("list")
    pl.add_argument("--limit", type=int, default=25)
    pl.add_argument("--page", type=int, default=1)
    pl.add_argument("--type")
    pl.add_argument("--source-type", dest="source_type")
    pl.add_argument("--status")
    pl.set_defaults(func=cmd_list)

    pg = sub.add_parser("get")
    pg.add_argument("--id", required=True)
    pg.set_defaults(func=cmd_get)

    ps = sub.add_parser("search")
    ps.add_argument("--query", required=True)
    ps.add_argument("--mode", choices=["semantic", "text"], default="semantic")
    ps.add_argument("--limit", type=int, default=10)
    ps.set_defaults(func=cmd_search)

    pd = sub.add_parser("duplicates")
    pd.add_argument("--limit", type=int, default=20)
    pd.add_argument("--offset", type=int, default=0)
    pd.set_defaults(func=cmd_duplicates)

    pc = sub.add_parser("capture")
    pc.add_argument("--content", required=True)
    pc.add_argument("--source-type", dest="source_type", default="manual")
    pc.set_defaults(func=cmd_capture)

    pr = sub.add_parser("repair-types", help="fill the `type` column on rows where it is NULL")
    pr.add_argument("--dry-run", dest="dry_run", action="store_true")
    pr.set_defaults(func=cmd_repair_types)

    pu = sub.add_parser("update")
    pu.add_argument("--id", required=True)
    pu.add_argument("--content")
    pu.add_argument("--metadata-patch", dest="metadata_patch")
    pu.add_argument("--type")
    pu.add_argument("--status")
    pu.add_argument("--importance", type=int)
    pu.add_argument("--quality-score", dest="quality_score", type=int)
    pu.add_argument("--sensitivity-tier", dest="sensitivity_tier")
    pu.set_defaults(func=cmd_update)

    pk = sub.add_parser("delete")
    pk.add_argument("--id", required=True)
    pk.add_argument("--yes", action="store_true")
    pk.set_defaults(func=cmd_delete)

    a = p.parse_args()
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:  # piped into head/less — exit quietly
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
