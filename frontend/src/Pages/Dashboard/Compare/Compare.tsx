import { ApiError } from "../../../api/client";
import type { Run } from "../../../api/types";
import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { GradeChip } from "../../../components/GradeChip";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, DataTable, EmptyState, ErrorState, Field, Panel, Select } from "../../../components/ui";
import { ago, fmt, humanize, METRIC_LABELS, METRIC_UNITS, metricRank, short } from "../../../components/ui/format";
import { useCompare } from "./useCompare";

const label = (r: Run) => `${r.grade ? `Grade ${r.grade}` : "No grade"} · ${r.target_name ?? "target"} · ${humanize(r.condition_profile_key)} · ${r.total_calls} calls · ${ago(r.created_at)}`;

const SUB_NAMES: Record<string, string> = { "SC-01": "Responsiveness", "SC-02": "Turn-taking", "SC-03": "Reliability", "SC-04": "Task quality", "SC-05": "Resilience" };

export default function Compare() {
  const { a, b, runs, result, pick, swap } = useCompare();
  const items = runs.data?.items ?? [];
  const err = result.error instanceof ApiError ? result.error : null;
  const r = result.data;
  return (
    <>
      <PageHeader eyebrow="A/B test for voice agents" title="Compare two configurations" subtitle="Two runs of the same suite and threshold version. A is the version you have today, B is the change you are considering; the rule below decides which to ship." actions={<Button onClick={swap} disabled={!a || !b}>Swap sides</Button>} />
      <Panel>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="A — baseline"><Select value={a} onChange={(e) => pick("a", e.target.value)}><option value="">choose a run…</option>{items.map((x) => <option key={x.id} value={x.id}>{label(x)}</option>)}</Select></Field>
          <Field label="B — candidate"><Select value={b} onChange={(e) => pick("b", e.target.value)}><option value="">choose a run…</option>{items.map((x) => <option key={x.id} value={x.id}>{label(x)}</option>)}</Select></Field>
        </div>
      </Panel>
      {items.length < 2 && <div className="mt-4"><EmptyState title="Two completed runs are needed">Runs are comparable when they executed the same suite version against the same threshold profile version. Run the example suite against both bundled targets to compare two real configurations.</EmptyState></div>}
      {err && (
        <div className="mt-4 rounded-lg border border-warn/50 bg-warn/10 p-4 text-sm">
          <b className="text-warn">Not comparable — {err.code.replace("_", " ")}.</b> {err.message}.
          {err.body?.a ? <div className="mt-1 mono text-xs">A: {String(err.body.a).slice(0, 16)}… · B: {String(err.body.b).slice(0, 16)}…</div> : null}
        </div>
      )}
      {result.isError && !err && <div className="mt-4"><ErrorState error={result.error} /></div>}
      {r && (
        <>
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            {(["a", "b"] as const).map((k) => {
              const winner = r.recommendation.recommendation === k.toUpperCase() || (r.recommendation.recommendation === "no_change" && k === "a");
              return (
                <Panel key={k} title={k === "a" ? "A — baseline" : "B — candidate"} className={winner ? "ring-accent" : ""}
                  actions={winner ? <span className="rounded-full bg-pass/10 px-2 py-0.5 text-[11px] font-semibold text-pass">recommended</span> : null}>
                  <div className="flex items-center gap-4">
                    <GradeChip grade={r[k].grade} size="lg" />
                    <div className="min-w-0">
                      <div className="text-4xl font-extrabold tracking-tight num">{fmt(r[k].overall, "", 2)}<span className="text-base font-medium text-muted"> / 100</span></div>
                      <div className="truncate font-semibold">{r[k].target}</div>
                      <div className="text-xs text-muted">{r[k].label} · {humanize(r[k].conditions)} · <span className="mono">{short(r[k].run_id)}</span></div>
                    </div>
                  </div>
                </Panel>
              );
            })}
            <Panel title="Recommendation">
              <div className="text-gradient text-3xl font-extrabold tracking-tight">{r.recommendation.recommendation === "no_change" ? "Keep A" : `Ship ${r.recommendation.recommendation}`}</div>
              <p className="mt-1 text-sm">{r.recommendation.rationale}</p>
              <Badge tone="info">rule {r.recommendation.rule_id}</Badge>
              <p className="mt-2 text-[11px] text-muted">R1 hard breach · R2 score gap beyond the band · R3 within band, cheaper wins · R4 no change. Deterministic.</p>
            </Panel>
          </div>
          <div className="mt-4">
            <Panel title="Per-metric" pad={false} actions={<EvidenceLabel kind="MEASURED" />}>
              <DataTable rows={[...r.metrics].sort((x, y) => metricRank(x.metric) - metricRank(y.metric))} rowKey={(m) => m.metric} columns={[
                { key: "m", header: "Metric", render: (m) => METRIC_LABELS[m.metric] ?? m.metric },
                { key: "a", header: "A", align: "right", render: (m) => <span className={m.a_status === "breach" ? "font-semibold text-breach" : ""}>{fmt(m.a, METRIC_UNITS[m.metric] === "×" ? "" : METRIC_UNITS[m.metric] ?? "")}</span> },
                { key: "b", header: "B", align: "right", render: (m) => <span className={m.b_status === "breach" ? "font-semibold text-breach" : ""}>{fmt(m.b, METRIC_UNITS[m.metric] === "×" ? "" : METRIC_UNITS[m.metric] ?? "")}</span> },
                { key: "d", header: "Δ (B − A)", align: "right", render: (m) => m.delta == null ? "—" : <span className={m.direction ? ((m.direction === "lower_is_better" ? m.delta > 0 : m.delta < 0) ? "text-breach" : "text-pass") : ""}>{m.delta > 0 ? "+" : ""}{fmt(m.delta)}</span> },
                { key: "t", header: "Threshold", align: "right", render: (m) => m.threshold == null ? <span className="text-muted">—</span> : <span className="text-muted">{fmt(m.threshold, METRIC_UNITS[m.metric] === "×" ? "" : METRIC_UNITS[m.metric] ?? "")}</span> },
              ]} />
            </Panel>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="Sub-scores" pad={false}>
              <DataTable rows={r.subscores} rowKey={(s) => s.id} columns={[
                { key: "i", header: "Sub-score", render: (s) => <span><span className="mono text-[11px] text-muted">{s.id}</span> {SUB_NAMES[s.id] ?? ""}</span> },
                { key: "a", header: "A", align: "right", render: (s) => fmt(s.a) },
                { key: "b", header: "B", align: "right", render: (s) => fmt(s.b) },
              ]} />
            </Panel>
            <Panel title="Estimated target cost per successful session" actions={<EvidenceLabel kind="ESTIMATED" />}>
              <div className="grid grid-cols-2 gap-4 num"><div><div className="text-xs text-muted">A</div><div className="text-xl font-semibold">{fmt(r.cost.a, "USD")}</div></div><div><div className="text-xs text-muted">B</div><div className="text-xl font-semibold">{fmt(r.cost.b, "USD")}</div></div></div>
              <p className="mt-2 text-xs text-muted">{r.cost.label}. Shown only when the target declared unit prices.</p>
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
