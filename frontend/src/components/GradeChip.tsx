import type { Grade } from "../api/types";

const tone: Record<string, string> = {
  A: "bg-pass/15 text-pass border-pass/50",
  B: "bg-pass/10 text-pass border-pass/40",
  C: "bg-warn/10 text-warn border-warn/50",
  D: "bg-breach/10 text-breach border-breach/50",
  F: "bg-breach/15 text-breach border-breach/60",
};

/** The grade chip is the largest colour element on any list (PRD 18.2). No grade is ever invented:
 *  a suppressed grade shows as "—" with the reason in its tooltip. */
export function GradeChip({ grade, size = "md", reason }: { grade: Grade | undefined; size?: "sm" | "md" | "lg"; reason?: string | null }) {
  const dims = size === "lg" ? "h-16 w-16 text-4xl" : size === "sm" ? "h-6 w-6 text-xs" : "h-9 w-9 text-lg";
  const cls = grade ? tone[grade] : "bg-panel2 text-muted border-line";
  return (
    <span title={grade ? `Grade ${grade}` : reason ?? "No grade emitted"}
      className={`inline-flex shrink-0 items-center justify-center rounded-md border font-bold ${dims} ${cls}`}>
      {grade ?? "—"}
    </span>
  );
}
