import { ApiError } from "../../../api/client";
import type { Run } from "../../../api/types";
import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { GradeChip } from "../../../components/GradeChip";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, DataTable, EmptyState, ErrorState, Field, Panel, Select } from "../../../components/ui";
import { fmt, METRIC_LABELS, short } from "../../../components/ui/format";
import { useCompare } from "./useCompare";

const label = (r: Run) => `${r.target_name ?? "target"} · ${r.label ?? r.condition_profile_key} · ${short(r.id)} · ${r.grade ?? "no grade"}`;

export default function Compare() {
  const { a, b, runs, result, pick, swap } = useCompare();
  const items = runs.data?.items ?? [];
  const err = result.error instanceof ApiError ? result.error : null;
  const r = result.data;
  return (
    <>
      <PageHeader title="Compare configurations" subtitle="Same suite version and threshold version, two runs. A = baseline, B = candidate." actions={<Button onClick={swap} disabled={!a || !b}>Swap sides</Button>} />
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
            {(["a", "b"] as const).map((k) => (
              <Panel key={k} title={k === "a" ? "A — baseline" : "B — candidate"}>
                <div className="flex items-center gap-3">
                  <GradeChip grade={r[k].grade} />
                  <div><div className="font-semibold">{r[k].target}</div><div className="text-xs text-muted">{r[k].label} · {r[k].conditions} · <span className="mono">{short(r[k].run_id)}</span></div></div>
                  <div className="ml-auto text-2xl font-bold num">{fmt(r[k].overall, "", 2)}</div>
                </div>
              </Panel>
            ))}
            <Panel title="Recommendation">
              <div className="text-2xl font-bold">{r.recommendation.recommendation === "no_change" ? "No change" : `Ship ${r.recommendation.recommendation}`}</div>
              <p className="mt-1 text-sm">{r.recommendation.rationale}</p>
              <Badge tone="info">rule {r.recommendation.rule_id}</Badge>
              <p className="mt-2 text-[11px] text-muted">R1 hard breach · R2 score gap beyond the band · R3 within band, cheaper wins · R4 no change. Deterministic.</p>
            </Panel>
          </div>
          <div className="mt-4">
            <Panel title="Per-metric" pad={false} actions={<EvidenceLabel kind="MEASURED" />}>
              <DataTable rows={r.metrics} rowKey={(m) => m.metric} columns={[
                { key: "m", header: "Metric", render: (m) => METRIC_LABELS[m.metric] ?? m.metric },
                { key: "a", header: "A", align: "right", render: (m) => <span className={m.a_status === "breach" ? "text-breach" : ""}>{fmt(m.a)}</span> },
                { key: "b", header: "B", align: "right", render: (m) => <span className={m.b_status === "breach" ? "text-breach" : ""}>{fmt(m.b)}</span> },
                { key: "d", header: "Δ (B − A)", align: "right", render: (m) => m.delta == null ? "—" : <span className={m.direction ? ((m.direction === "lower_is_better" ? m.delta > 0 : m.delta < 0) ? "text-breach" : "text-pass") : ""}>{m.delta > 0 ? "+" : ""}{fmt(m.delta)}</span> },
                { key: "t", header: "Threshold", align: "right", render: (m) => m.threshold ?? "—" },
              ]} />
            </Panel>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="Sub-scores" pad={false}>
              <DataTable rows={r.subscores} rowKey={(s) => s.id} columns={[
                { key: "i", header: "Sub-score", render: (s) => s.id },
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
