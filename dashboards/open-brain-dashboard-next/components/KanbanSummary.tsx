"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import type { KanbanStatus } from "@/lib/types";
import { KANBAN_STATUSES, KANBAN_LABELS } from "@/lib/types";

// Same badge recipe as ThoughtCard: 10% tint, 20% border, muted label.
const STATUS_COLORS: Record<string, string> = {
  new: "bg-white/5 text-text-secondary border-border",
  planning: "bg-sky-400/10 text-sky-300/90 border-sky-400/20",
  active: "bg-violet/10 text-violet border-violet/25",
  review: "bg-amber-400/10 text-amber-300/90 border-amber-400/20",
  done: "bg-white/5 text-text-muted border-border",
};

export function KanbanSummary() {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch("/api/kanban")
      .then((res) => res.json())
      .then((data) => {
        const grouped: Record<string, number> = {};
        for (const s of KANBAN_STATUSES) grouped[s] = 0;
        for (const t of data.thoughts || []) {
          const status = t.status ?? "new";
          if (grouped[status] !== undefined) grouped[status]++;
        }
        setCounts(grouped);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const totalActive = (counts.active || 0) + (counts.planning || 0) + (counts.review || 0);

  if (isLoading) {
    return (
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <div className="h-4 w-32 bg-bg-hover rounded animate-pulse mb-3" />
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-6 w-16 bg-bg-hover rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <Link href="/kanban" className="block group">
      <div className="bg-bg-surface border border-border rounded-lg p-5 hover:border-border-strong transition-colors">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-text-primary">Workflow</h2>
          <span className="text-xs text-text-muted group-hover:text-violet transition-colors">
            Open workflow →
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {KANBAN_STATUSES.map((status) => {
            const count = counts[status] || 0;
            if (count === 0 && status === "done") return null;
            const colorClass = STATUS_COLORS[status] || STATUS_COLORS.new;
            return (
              <span
                key={status}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${colorClass}`}
              >
                {KANBAN_LABELS[status as KanbanStatus]}
                <span className="font-bold">{count}</span>
              </span>
            );
          })}
        </div>
        {totalActive > 0 && (
          <p className="text-xs text-text-muted mt-2">
            {totalActive} item{totalActive !== 1 ? "s" : ""} in progress
          </p>
        )}
      </div>
    </Link>
  );
}
