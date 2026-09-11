// Number and time formatting used by every page. A number never appears without its unit.

export function fmt(v: number | null | undefined, unit = "", digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  const d = abs >= 1000 ? 0 : abs >= 100 ? Math.min(digits, 1) : digits;
  const s = v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: 0 });
  if (!unit) return s;
  if (unit === "%") return `${s}%`;
  if (unit === "USD") return `$${v.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
  return `${s} ${unit}`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return `${Math.max(0, Math.round(s))}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function dur(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

// Identifiers are UUID v7: the leading characters encode time and are shared by rows created together,
// so the random tail is what tells two calls of one run apart.
export const short = (id: string | null | undefined, n = 8) => (id ? id.replace(/-/g, "").slice(-n) : "—");

export function passes(value: number | null | undefined, threshold?: number, direction?: string): boolean | null {
  if (value === null || value === undefined || threshold === undefined) return null;
  return direction === "higher_is_better" ? value >= threshold : value <= threshold;
}

export const METRIC_LABELS: Record<string, string> = {
  response_latency_p50: "Response latency p50",
  response_latency_p95: "Response latency p95",
  response_latency_p99: "Response latency p99",
  time_to_first_response_p50: "Time to first response",
  barge_in_stop_p95: "Barge-in stop p95",
  yield_rate: "Yield rate",
  talkover_mean: "Talk-over / call",
  dead_air_ratio: "Dead-air ratio",
  call_completion_rate: "Call completion",
  session_error_rate: "Session errors",
  task_success_rate: "Task success",
  needs_review_rate: "Needs review",
  degradation_ratio: "Degradation ratio",
  est_cost_per_session: "Est. target cost / session",
  est_cost_per_successful_session: "Est. target cost / success",
  rig_overhead_p95: "Rig overhead p95",
  cache_hit_rate: "Utterance cache hits",
  fallback_rate: "Caller fallback rate",
  premature_speech_rate: "Premature speech",
  reconnect_rate: "Reconnects",
};
