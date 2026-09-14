import { useEffect, useState } from "react";
import type { Grade } from "../api/types";

const TONE: Record<string, string> = { A: "var(--color-pass)", B: "var(--color-pass)", C: "var(--color-warn)", D: "var(--color-breach)", F: "var(--color-breach)" };

/** The readiness score as a ring that fills to its value on first paint. The grade letter sits in the
 *  middle; with no grade the ring stays empty and shows why, so a missing grade never looks like a zero. */
export function ScoreRing({ score, grade, size = 132 }: { score: number | null | undefined; grade: Grade | undefined; size?: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const t = requestAnimationFrame(() => setShown(score ?? 0));
    return () => cancelAnimationFrame(t);
  }, [score]);
  const stroke = 11;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const color = grade ? TONE[grade] : "var(--color-muted)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img"
      aria-label={grade ? `Grade ${grade}, score ${score} out of 100` : "No grade emitted"}>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-panel2)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={circ * (1 - Math.min(100, Math.max(0, shown)) / 100)}
          style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.2,.7,.2,1)" }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-4xl font-extrabold leading-none tracking-tight" style={{ color }}>{grade ?? "—"}</div>
          <div className="mt-1 text-xs font-medium text-muted num">{score != null ? `${score.toFixed(score % 1 ? 2 : 0)} / 100` : "no grade"}</div>
        </div>
      </div>
    </div>
  );
}
