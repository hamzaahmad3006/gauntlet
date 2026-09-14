import type { ReactNode } from "react";

/** A value is never shown without the threshold it is judged against (PRD 18.1 rule 1). */
export function Stat({ label, value, threshold, status, sub, plain = false }:
  { label: string; value: ReactNode; threshold?: ReactNode; status?: boolean | null; sub?: ReactNode; plain?: boolean }) {
  const tone = status === true ? "text-pass" : status === false ? "text-breach" : "text-fg";
  return (
    <div className={`min-w-0 ${plain ? "rounded-xl bg-panel2/70 px-3 py-2.5" : "glass rounded-xl px-4 py-3"}`}>
      <div className="truncate text-[11px] uppercase tracking-[0.12em] text-muted">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tracking-tight num ${tone}`}>{value}</div>
      {threshold !== undefined && <div className="text-xs text-muted num">threshold {threshold}</div>}
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}
