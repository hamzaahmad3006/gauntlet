import type { ReactNode } from "react";

export type Tone = "pass" | "breach" | "warn" | "info" | "live" | "muted";

const tones: Record<Tone, string> = {
  pass: "text-pass border-pass/50 bg-pass/10",
  breach: "text-breach border-breach/50 bg-breach/10",
  warn: "text-warn border-warn/50 bg-warn/10",
  info: "text-info border-info/50 bg-info/10",
  live: "text-live border-live/50 bg-live/10",
  muted: "text-muted border-line bg-panel2",
};

export function Badge({ tone = "muted", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  );
}
