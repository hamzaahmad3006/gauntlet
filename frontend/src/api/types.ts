// Response shapes shared by pages. Kept deliberately close to the API's JSON.

export type Grade = "A" | "B" | "C" | "D" | "F" | null;
export type RunStatus = "queued" | "running" | "completed" | "aborted" | "aborted_budget" | "failed";
export type CallStatus = "pending" | "dialling" | "in_call" | "scoring" | "completed" | "failed" | "needs_review" | "errored";

export interface Run {
  id: string;
  target_id: string;
  target_name?: string;
  suite_id: string;
  suite_version_hash: string;
  condition_profile_key: string;
  condition_parameters: Record<string, unknown>;
  threshold_profile_key: string;
  threshold_version_hash: string;
  definitions_version: string;
  seed: string;
  concurrency_requested: number;
  concurrency_effective: number;
  concurrency_peak: number | null;
  repeats: number;
  total_calls: number;
  status: RunStatus;
  flags: string[];
  spend_cap_usd: number;
  rig_cost_usd: number | null;
  estimated_target_cost_usd: number | null;
  grade: Grade;
  overall: number | null;
  label: string | null;
  current_epoch: number;
  epochs: { epoch: number; parameters: Record<string, unknown>; profile?: string | null; effective_at: string }[];
  providers: Record<string, boolean> | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  headline?: Record<string, number | null>;
}

export interface Target {
  id: string;
  name: string;
  adapter: "livekit" | "websocket_pcm";
  description: string | null;
  bundled: boolean;
  connection_hint: string | null;
  verified_at: string | null;
  pipeline_declaration: Record<string, unknown> | null;
  unit_prices: Record<string, Record<string, number>> | null;
  cost_model_declared: boolean;
  last_diagnostic: Diagnostic | null;
  baseline_run_id: string | null;
  speech_margin_db: number | null;
  created_at: string;
  last_run: Run | null;
}

export interface DiagStatus {
  status: "ok" | "failed" | "not_reached" | "not_configured";
  hint?: string;
  reason?: string;
  [k: string]: unknown;
}
export interface Diagnostic {
  connection: DiagStatus;
  audio_out: DiagStatus;
  audio_in: DiagStatus;
  transcript: DiagStatus;
  checked_at?: string;
}

export interface Scenario {
  key: string;
  coverage_tag: "happy_path" | "edge_case" | "adversarial" | "out_of_scope";
  description?: string;
  persona_key?: string;
  objective: string;
  goal_checklist: { id: string; text: string }[];
  opening_utterance: string;
  fallback_lines: string[];
  behaviour_policies?: Record<string, Record<string, unknown>>;
  timing?: Record<string, number>;
  success_criteria?: Record<string, unknown>;
}
export interface Persona {
  key: string;
  description?: string;
  voice_id: string;
  speech_rate: number;
  patience_s: number;
  verbosity?: string;
  interruption_tendency?: number;
  disfluency?: string;
}
export interface Suite {
  id: string;
  key: string;
  name: string;
  version_hash: string;
  domain?: string;
  description?: string;
  scenarios: Scenario[];
  personas: Persona[];
  created_at: string;
}
export interface ConditionProfile {
  key: string;
  parameters: Record<string, Record<string, unknown>>;
  active: boolean;
  interruptions_per_call: number;
}
export interface ThresholdProfile {
  key: string;
  version_hash: string;
  document: {
    metrics: Record<string, { ideal: number; threshold: number; limit: number; direction: string; unit?: string }>;
    subscores: Record<string, { name: string; weight: number; inputs: Record<string, number> }>;
    hard_breaches: Record<string, number>;
  };
}

export interface MetricRow {
  name: string;
  value: number | null;
  n: number;
  unit: string;
  normalised: number | null;
  flags: string[];
  epoch: number | null;
}

export interface SubScore {
  id: string;
  name: string;
  weight: number;
  effective_weight: number;
  score: number | null;
  available: boolean;
  contribution: number | null;
  inputs: {
    metric: string;
    value: number | null;
    normalised: number | null;
    intra_weight: number;
    effective_weight: number;
    status: "pass" | "breach" | "missing";
  }[];
}

export interface Score {
  overall: number | null;
  grade: Grade;
  flags: string[];
  caps: string[];
  suppressed_reason: string | null;
  missing_metrics: string[];
  subscores: SubScore[];
  epochs: { epoch: number; n: number; p50: number | null; p95: number | null; flags: string[] }[];
  completed_calls: number;
}

export interface Call {
  id: string;
  run_id: string;
  scenario_key: string;
  persona_key: string;
  coverage_tag: string;
  repeat_index: number;
  seed: string;
  interruption_schedule: { turn_idx: number; offset_ms: number }[];
  status: CallStatus;
  reason_code: string | null;
  attempt: number;
  talkover_ms: number | null;
  dead_air_ratio: number | null;
  duration_ms: number | null;
  cache_hit_rate: number | null;
  achieved_impairment: Record<string, unknown> | null;
  interruptions: { turn_idx: number; scheduled_offset_ms: number; status: string; barge_stop_ms: number | null; no_yield: boolean }[] | null;
  fallbacks: Record<string, number>;
  flags: string[];
  referee_engine: string | null;
  referee_error: string | null;
  connect_ms: number | null;
  has_audio: boolean;
}

export interface RunSummary {
  run: Run;
  score: Score | null;
  target: { id: string; name: string; adapter: string; bundled: boolean; baseline_run_id: string | null; cost_model_declared: boolean } | null;
  metrics: MetricRow[];
  calls: Call[];
  threshold_document: ThresholdProfile["document"];
  live: { active?: number; peak?: number; spend_usd?: number };
  calibration: { bound_ms: number; scope: string } | null;
  disclosure: string;
  disclosures: Record<string, string>;
}

export interface Turn {
  idx: number;
  caller_text: string | null;
  agent_text: string | null;
  agent_confidence: number | null;
  latency_ms: number | null;
  raw_latency_ms: number | null;
  censored: boolean;
  premature: boolean;
  rig_overhead_ms: number | null;
  barge_stop_ms: number | null;
  no_yield: boolean;
  interruption_status: string | null;
  fallback_used: boolean;
  epoch: number;
  t_caller_first_voiced_ms: number | null;
  t_caller_last_sample_ms: number | null;
  t_agent_first_audio_ms: number | null;
  t_agent_last_audio_ms: number | null;
}

export interface CallDetail {
  call: Call;
  turns: Turn[];
  events: { t_ms: number; kind: string; payload: Record<string, unknown> }[];
  verdict: {
    task_success: boolean | null;
    status: string;
    needs_review: boolean;
    agreement: number | null;
    steps: { step_id: string; text: string; met: boolean; turn_index: number | null; quote: string | null; demoted?: string }[];
    model: string;
    prompt_version: string;
  } | null;
  intervals_ms: { caller: [number, number][]; agent: [number, number][]; windows: [number, number][] };
}

export interface Waveform {
  available: boolean;
  reason?: string;
  bin_ms?: number;
  caller?: number[];
  agent?: number[];
}

export interface CompareResult {
  a: { run_id: string; overall: number | null; grade: Grade; label: string; target?: string; conditions?: string; status?: string };
  b: { run_id: string; overall: number | null; grade: Grade; label: string; target?: string; conditions?: string; status?: string };
  metrics: { metric: string; a: number | null; b: number | null; delta: number | null; threshold?: number; direction?: string; a_status?: string; b_status?: string }[];
  subscores: { id: string; a: number | null; b: number | null }[];
  cost: { a: number | null; b: number | null; label: string };
  recommendation: { recommendation: string; rule_id: string; rationale: string };
}

export interface ReportData {
  run_id: string;
  status: string;
  grade: Grade;
  overall: number | null;
  suppressed_reason: string | null;
  caps: string[];
  flags: string[];
  subscores: SubScore[];
  metrics: { name: string; met_id: string; label: string; value: number | null; unit: string; n: number; flags: string[]; threshold: number | null; status: string | null; evidence: string; definition: string }[];
  target: string;
  suite: { name: string; version_hash: string };
  seed: string;
  conditions: { profile: string; parameters: Record<string, unknown> };
  thresholds: { profile: string; version_hash: string };
  concurrency: { requested: number; effective: number; peak_measured: number | null };
  cost: { rig_usd: number | null; pricing_flags: string[]; estimated_target_usd: number | null; estimated_label: string };
  calibration: { bound_ms: number; n: number; git_sha: string; environment: string; scope: string } | null;
  methodology: Record<string, string>;
  limitations: string[];
  created_at: string;
}

export interface SystemInfo {
  environment: string;
  providers: Record<string, boolean>;
  auth: { supabase_url: string; supabase_anon_key: string; dev_login: boolean; guest?: boolean };
  metrics: Record<string, { met_id: string; label: string; unit: string; direction: string; definition: string }>;
  disclosures: Record<string, string>;
  limits: Record<string, number>;
  calibration: Calibration | null;
}

export interface Calibration {
  bound_ms: number | null;
  acceptable_max_ms?: number;
  passed?: boolean;
  n?: number;
  delays_ms?: number[];
  repetitions?: number;
  method?: string;
  scope?: string;
  per_level?: Record<string, { n: number; max_abs_error_ms: number; mean_error_ms: number; stdev_error_ms: number; mean_target_overshoot_ms: number }>;
  git_sha?: string;
  run_at?: string;
  environment?: string;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface Gate {
  id: string;
  run_id: string;
  baseline_run_id: string;
  verdict: "passed" | "failed" | "error";
  breaches: { kind: string; metric: string; baseline: number | null; candidate: number | null; delta: number | null }[];
  markdown: string;
  created_at: string;
}

export interface Estimate {
  calls: number;
  concurrency_effective: number;
  estimated_duration_s: number;
  estimated_rig_cost_usd: number;
  assumptions: string[];
}

export interface LiveEvent {
  id: string;
  kind: string;
  seq: number;
  ts?: number;
  [k: string]: unknown;
}
