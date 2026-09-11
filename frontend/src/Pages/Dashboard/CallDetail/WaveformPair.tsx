import { useEffect, useRef } from "react";
import type { Turn, Waveform } from "../../../api/types";

/** Caller (top) and agent (bottom) peaks on one time axis, overlap regions filled, turn latencies and
 *  interruption markers drawn at their measured instants. Both channels come from one recording on one
 *  clock, so their alignment is exact by construction. */
export function WaveformPair({ wf, turns, intervals, cursorMs }:
  { wf: Waveform; turns: Turn[]; intervals: { caller: [number, number][]; agent: [number, number][] }; cursorMs?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !wf.available || !wf.caller || !wf.agent) return;
    const dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, H = 160;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d")!;
    g.scale(dpr, dpr);
    const css = getComputedStyle(document.documentElement);
    const col = (n: string) => css.getPropertyValue(n).trim() || "#888";
    const n = wf.caller.length;
    const binMs = wf.bin_ms ?? 10;
    const totalMs = n * binMs;
    const x = (ms: number) => (ms / totalMs) * W;
    g.clearRect(0, 0, W, H);
    // overlap (talk-over) regions
    g.fillStyle = col("--color-breach") + "33";
    for (const [cs, ce] of intervals.caller) for (const [as_, ae] of intervals.agent) {
      const s = Math.max(cs, as_), e = Math.min(ce, ae);
      if (e > s) g.fillRect(x(s), 0, Math.max(1, x(e) - x(s)), H);
    }
    const lane = (vals: number[], y0: number, h: number, color: string) => {
      g.fillStyle = color;
      const step = Math.max(1, Math.floor(n / W));
      for (let i = 0; i < n; i += step) {
        let m = 0;
        for (let j = i; j < Math.min(n, i + step); j++) m = Math.max(m, vals[j]);
        const amp = Math.min(1, m * 3) * (h / 2);
        g.fillRect(x(i * binMs), y0 + h / 2 - amp, Math.max(1, W / n * step), amp * 2 || 0.5);
      }
    };
    lane(wf.caller, 8, 64, col("--color-info"));
    lane(wf.agent, 88, 64, col("--color-pass"));
    g.fillStyle = col("--color-muted");
    g.font = "10px sans-serif";
    g.fillText("caller", 4, 14);
    g.fillText("agent", 4, 94);
    // turn latency spans and interruption markers
    for (const t of turns) {
      if (t.t_caller_last_sample_ms != null && t.t_agent_first_audio_ms != null && t.latency_ms != null) {
        g.strokeStyle = col("--color-warn");
        g.beginPath(); g.moveTo(x(t.t_caller_last_sample_ms), 80); g.lineTo(x(t.t_agent_first_audio_ms), 80); g.stroke();
        g.fillStyle = col("--color-warn");
        g.fillText(`${Math.round(t.latency_ms)}`, x(t.t_caller_last_sample_ms) + 2, 78);
      }
    }
    if (cursorMs != null) {
      g.strokeStyle = col("--color-fg");
      g.beginPath(); g.moveTo(x(cursorMs), 0); g.lineTo(x(cursorMs), H); g.stroke();
    }
  }, [wf, turns, intervals, cursorMs]);
  if (!wf.available) return <div className="rounded-md border border-dashed border-line p-6 text-center text-sm text-muted">{wf.reason ?? "audio unavailable"}</div>;
  return <canvas ref={ref} className="h-40 w-full" role="img" aria-label="Caller and agent waveforms with talk-over regions and per-turn latency" />;
}
