import type { ReactNode } from "react";

/** A value is never shown without the threshold it is judged against (PRD 18.1 rule 1). */
export function Stat({ label, value, threshold, status, sub }:
  { label: string; value: ReactNode; threshold?: ReactNode; status?: boolean | null; sub?: ReactNode }) {
  const tone = status === true ? "text-pass" : status === false ? "text-breach" : "text-fg";
  return (
    <div className="glass min-w-0 rounded-xl px-4 py-3">
      <div className="truncate text-[11px] uppercase tracking-[0.12em] text-muted">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tracking-tight num ${tone}`}>{value}</div>
      {threshold !== undefined && <div className="text-xs text-muted num">threshold {threshold}</div>}
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}
