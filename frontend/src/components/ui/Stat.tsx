import type { ReactNode } from "react";

/** A value is never shown without the threshold it is judged against (PRD 18.1 rule 1). */
export function Stat({ label, value, threshold, status, sub }:
  { label: string; value: ReactNode; threshold?: ReactNode; status?: boolean | null; sub?: ReactNode }) {
  const tone = status === true ? "text-pass" : status === false ? "text-breach" : "text-fg";
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wider text-muted truncate">{label}</div>
      <div className={`text-xl font-semibold num ${tone}`}>{value}</div>
      {threshold !== undefined && <div className="text-xs text-muted num">threshold {threshold}</div>}
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}
