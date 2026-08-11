import Link from "next/link";
import type { Thought } from "@/lib/types";
import { FormattedDate } from "@/components/FormattedDate";

// One badge recipe applied across every type: 10% tint, 20% border, solid label.
// Hues stay desaturated so the green accent remains the only loud colour.
const typeColors: Record<string, string> = {
  idea: "bg-amber-400/10 text-amber-300/90 border-amber-400/20",
  task: "bg-sky-400/10 text-sky-300/90 border-sky-400/20",
  person_note: "bg-teal-400/10 text-teal-300/90 border-teal-400/20",
  reference: "bg-white/5 text-text-secondary border-border",
  decision: "bg-violet/10 text-violet border-violet/20",
  lesson: "bg-orange-400/10 text-orange-300/90 border-orange-400/20",
  meeting: "bg-cyan-400/10 text-cyan-300/90 border-cyan-400/20",
  journal: "bg-rose-400/10 text-rose-300/90 border-rose-400/20",
};

export function TypeBadge({ type }: { type: string }) {
  const colors = typeColors[type] || typeColors.reference;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${colors}`}
    >
      {type}
    </span>
  );
}

export function ThoughtCard({
  thought,
  showLink = true,
}: {
  thought: Thought;
  showLink?: boolean;
}) {
  const preview =
    thought.content.length > 200
      ? thought.content.slice(0, 200) + "..."
      : thought.content;

  const inner = (
    <div className="bg-bg-surface border border-border rounded-lg p-4 hover:border-border-strong hover:bg-bg-elevated transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <TypeBadge type={thought.type} />
          {thought.importance > 0 && (
            <span className="text-xs text-text-muted">
              imp: {thought.importance}
            </span>
          )}
        </div>
        <FormattedDate date={thought.created_at} className="text-xs text-text-muted whitespace-nowrap" />
      </div>
      <p className="text-sm text-text-secondary leading-relaxed">{preview}</p>
      {thought.source_type && (
        <span className="inline-block mt-2 text-xs text-text-muted">
          {thought.source_type}
        </span>
      )}
    </div>
  );

  if (showLink) {
    return <Link href={`/thoughts/${thought.id}`}>{inner}</Link>;
  }
  return inner;
}
