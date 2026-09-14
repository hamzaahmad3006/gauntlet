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

// The unit each metric is reported in, so tables never show a bare number.
export const METRIC_UNITS: Record<string, string> = {
  response_latency_p50: "ms", response_latency_p95: "ms", response_latency_p99: "ms", time_to_first_response_p50: "ms",
  barge_in_stop_p95: "ms", talkover_mean: "ms", rig_overhead_p95: "ms",
  yield_rate: "%", dead_air_ratio: "%", call_completion_rate: "%", session_error_rate: "%", task_success_rate: "%",
  needs_review_rate: "%", cache_hit_rate: "%", fallback_rate: "%", premature_speech_rate: "%", reconnect_rate: "%",
  degradation_ratio: "×", est_cost_per_session: "USD", est_cost_per_successful_session: "USD",
};

// Reading order for metric tables: what a caller feels first, rig diagnostics last.
export const METRIC_ORDER = [
  "response_latency_p95", "time_to_first_response_p50", "dead_air_ratio", "barge_in_stop_p95", "yield_rate", "talkover_mean",
  "task_success_rate", "call_completion_rate", "session_error_rate", "degradation_ratio", "response_latency_p50",
  "response_latency_p99", "premature_speech_rate", "needs_review_rate", "est_cost_per_session", "est_cost_per_successful_session",
  "fallback_rate", "cache_hit_rate", "rig_overhead_p95", "reconnect_rate",
];
export const metricRank = (m: string) => { const i = METRIC_ORDER.indexOf(m); return i < 0 ? 99 : i; };

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

// Keys such as "book_table_basic" are identifiers; people read "Book table basic".
export const humanize = (key: string | null | undefined): string =>
  key ? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "—";

// A condition profile's parameters in words, one phrase per impairment stage.
export function describeConditions(params: Record<string, unknown> | null | undefined): string[] {
  const p = (params ?? {}) as Record<string, Record<string, number | string>>;
  const out: string[] = [];
  if (p.frame_loss) out.push(`${fmt(Number(p.frame_loss.loss_probability) * 100, "%")} packet loss${p.frame_loss.burst_length ? `, bursts of ${p.frame_loss.burst_length}` : ""}`);
  if (p.jitter) out.push(`${fmt(Number(p.jitter.mean_ms), "", 0)} ± ${fmt(Number(p.jitter.stddev_ms), "ms", 0)} jitter`);
  if (p.delay) out.push(`+${fmt(Number(p.delay.delay_ms), "ms", 0)} delay`);
  if (p.noise) out.push(`${humanize(String(p.noise.noise_bed))} noise at ${p.noise.snr_db} dB SNR`);
  if (p.interruption) out.push(`${p.interruption.interruptions_per_call} interruptions per call`);
  if (p.slow_caller) out.push(`hesitant caller, ${fmt(Number(p.slow_caller.pause_ms), "ms", 0)} pauses`);
  return out;
}
