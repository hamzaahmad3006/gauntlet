// Every backend path, with its SRS API id. Pages never build a URL string themselves.
const enc = encodeURIComponent;

export const endpoints = {
  healthz: () => "/healthz", // API-070
  me: () => "/v1/me", // API-001
  system: () => "/v1/system",
  calibration: () => "/v1/calibration", // API-060

  apiKeys: () => "/v1/api-keys", // API-002, API-003
  apiKey: (id: string) => `/v1/api-keys/${enc(id)}`, // API-004

  targets: () => "/v1/targets", // API-010, API-011
  target: (id: string) => `/v1/targets/${enc(id)}`, // API-014
  verifyTarget: (id: string) => `/v1/targets/${enc(id)}/verify`, // API-012
  diagnoseTarget: (id: string) => `/v1/targets/${enc(id)}/diagnose`, // API-013
  baseline: (id: string) => `/v1/targets/${enc(id)}/baseline`, // API-051

  suites: () => "/v1/suites", // API-020, API-021
  suite: (id: string) => `/v1/suites/${enc(id)}`,
  conditionProfiles: () => "/v1/condition-profiles",
  thresholdProfiles: () => "/v1/threshold-profiles", // API-022

  runs: (q = "") => `/v1/runs${q}`, // API-030, API-032
  estimate: () => "/v1/runs/estimate", // API-031
  run: (id: string) => `/v1/runs/${enc(id)}`, // API-036
  abort: (id: string) => `/v1/runs/${enc(id)}/abort`, // API-033
  conditions: (id: string) => `/v1/runs/${enc(id)}/conditions`, // API-035
  events: (id: string) => `/v1/runs/${enc(id)}/events`, // API-034
  report: (id: string) => `/v1/runs/${enc(id)}/report.json`, // API-041
  reportMd: (id: string) => `/v1/runs/${enc(id)}/report.md`, // API-043
  share: (id: string) => `/v1/runs/${enc(id)}/share`, // API-042

  call: (id: string) => `/v1/calls/${enc(id)}`, // API-040
  callAudio: (id: string) => `/v1/calls/${enc(id)}/audio`,
  callWaveform: (id: string) => `/v1/calls/${enc(id)}/waveform`,

  compare: (a: string, b: string) => `/v1/compare?a=${enc(a)}&b=${enc(b)}`, // API-050
  gate: () => "/v1/gate", // API-052
  gates: () => "/v1/gates",

  publicReport: (token: string) => `/public/reports/${enc(token)}.json`, // API-044
};
