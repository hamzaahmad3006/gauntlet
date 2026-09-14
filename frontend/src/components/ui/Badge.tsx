import type { ReactNode } from "react";

export type Tone = "pass" | "breach" | "warn" | "info" | "live" | "muted";

const tones: Record<Tone, string> = {
  pass: "text-pass border-pass/40 bg-pass/10",
  breach: "text-breach border-breach/40 bg-breach/10",
  warn: "text-warn border-warn/40 bg-warn/10",
  info: "text-info border-info/40 bg-info/10",
  live: "text-live border-live/40 bg-live/10",
  muted: "text-muted border-line bg-panel2/70",
};

export function Badge({ tone = "muted", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none ${tones[tone]}`}>
      {children}
    </span>
  );
}
