import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Call, MetricRow, SubScore } from "../../../api/types";
import { Disclosure } from "../../../components/Disclosure";
import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { ScoreRing } from "../../../components/ScoreRing";
import { PageHeader } from "../../../components/Layout";
import { RunStatus } from "../../../components/RunStatus";
import { Badge, Button, DataTable, ErrorState, Panel, Skeleton } from "../../../components/ui";
import { dur, fmt, humanize, METRIC_LABELS, passes, short } from "../../../components/ui/format";
import { useResults } from "./useResults";

const ORDER = ["response_latency_p50", "response_latency_p95", "response_latency_p99", "time_to_first_response_p50", "barge_in_stop_p95",
  "yield_rate", "talkover_mean", "dead_air_ratio", "premature_speech_rate", "call_completion_rate", "session_error_rate", "task_success_rate",
  "needs_review_rate", "degradation_ratio", "est_cost_per_session", "est_cost_per_successful_session", "rig_overhead_p95", "cache_hit_rate",
  "fallback_rate", "reconnect_rate"];

function SubScoreRow({ s }: { s: SubScore }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-line/60 last:border-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-panel2" aria-expanded={open}>
        <span className="w-12 mono text-xs text-muted">{s.id}</span>
        <span className="flex-1 text-sm">{s.name}</span>
        <span className="w-20 text-right text-xs text-muted num">w {s.weight}{s.contribution != null && s.effective_weight !== s.weight ? ` → ${s.effective_weight}` : ""}</span>
        <span className={`w-16 text-right font-semibold num ${!s.available ? "text-muted" : (s.score ?? 0) >= 70 ? "text-pass" : "text-breach"}`}>{s.available ? fmt(s.score, "", 1) : "n/a"}</span>
        <span className="text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="bg-bg px-4 pb-3">
          {!s.available && <p className="py-2 text-xs text-muted">Unavailable: none of its inputs was measured in this run, so its weight was redistributed.</p>}
          <table className="w-full text-xs num">
            <thead><tr className="text-muted"><th className="py-1 text-left font-normal">input</th><th className="text-right font-normal">value</th><th className="text-right font-normal">normalised</th><th className="text-right font-normal">weight</th><th className="text-right font-normal">status</th></tr></thead>
            <tbody>
              {s.inputs.map((i) => (
                <tr key={i.metric}><td className="py-0.5">{METRIC_LABELS[i.metric] ?? i.metric}</td><td className="text-right">{fmt(i.value)}</td>
                  <td className="text-right">{fmt(i.normalised)}</td><td className="text-right">{i.intra_weight}{i.status !== "missing" && i.effective_weight !== i.intra_weight ? ` → ${i.effective_weight}` : ""}</td>
                  <td className="text-right"><Badge tone={i.status === "pass" ? "pass" : i.status === "breach" ? "breach" : "muted"}>{i.status}</Badge></td></tr>
              ))}
            </tbody>
          </table>
          {s.contribution != null && <p className="mt-1 text-xs text-muted">Contributes {fmt(s.contribution)} points to the overall score.</p>}
        </div>
      )}
    </div>
  );
}

export default function Results() {
  const { id, summary, promote, share, markdown } = useResults();
  const nav = useNavigate();
  if (summary.isLoading) return <Skeleton rows={8} />;
  if (summary.isError) return <ErrorState error={summary.error} retry={() => summary.refetch()} />;
  const s = summary.data!;
  const run = s.run;
  const score = s.score;
  const doc = s.threshold_document;
  const rank = (n: string) => (ORDER.indexOf(n) < 0 ? 999 : ORDER.indexOf(n));
  const metrics = s.metrics.filter((m) => m.epoch === null).sort((a, b) => rank(a.name) - rank(b.name));
  const breachFirst = [...metrics].sort((a, b) => {
    const pa = passes(a.value, doc.metrics[a.name]?.threshold, doc.metrics[a.name]?.direction) === false ? 0 : 1;
    const pb = passes(b.value, doc.metrics[b.name]?.threshold, doc.metrics[b.name]?.direction) === false ? 0 : 1;
    return pa - pb;
  });
  const outcomes = s.calls.reduce<Record<string, number>>((acc, c) => ({ ...acc, [c.status]: (acc[c.status] ?? 0) + 1 }), {});
  const inflight = run.status === "queued" || run.status === "running";
  const isBaseline = s.target?.baseline_run_id === run.id;
  return (
    <>
      <PageHeader
        title={<span className="flex items-center gap-3">{s.target?.name} <RunStatus run={run} /></span>}
        subtitle={<><span className="mono">run {short(run.id)}</span> · {humanize(run.condition_profile_key)} network · seed <span className="mono">{run.seed}</span> · {run.total_calls} calls · {new Date(run.created_at).toLocaleString()}</>}
        actions={<>
          {inflight && <Link to={`/dashboard/runs/${id}/live`}><Button variant="primary">Live view</Button></Link>}
          {!inflight && <Link to={`/dashboard/runs/${id}/live`}><Button>Replay</Button></Link>}
          <Button onClick={() => nav(`/dashboard/compare?b=${id}`)}>Compare</Button>
          <Button busy={markdown.isPending} onClick={() => markdown.mutate()}>{markdown.isSuccess ? "Markdown copied" : "Copy Markdown"}</Button>
          <Button busy={share.isPending} onClick={() => share.mutate()}>Share link</Button>
          <Link to={`/dashboard/runs/${id}/report`}><Button>Report</Button></Link>
          <Button variant="primary" disabled={isBaseline || !run.grade} busy={promote.isPending} onClick={() => promote.mutate()}>{isBaseline ? "Baseline" : "Promote to baseline"}</Button>
        </>}
      />
      {share.data && <div className="mb-4 rounded-md border border-pass/40 bg-pass/5 p-3 text-sm">Read-only link (no workspace identifiers): <a className="mono underline" href={share.data.url}>{share.data.url}</a></div>}
      {promote.isError && <div className="mb-4"><ErrorState error={promote.error} /></div>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Verdict">
          <div className="flex items-center gap-5">
            <ScoreRing score={run.overall} grade={run.grade} />
            <div className="min-w-0">
              <div className="text-sm font-semibold">Readiness score</div>
              <p className="mt-1 text-xs text-muted">Arithmetic over the measured metrics against threshold profile <span className="mono">{run.threshold_profile_key}@{run.threshold_version_hash.slice(0, 8)}</span>. No model assigns it.</p>
            </div>
          </div>
          {score?.suppressed_reason && <p className="mt-3 rounded bg-warn/10 p-2 text-sm text-warn">No grade emitted — {score.suppressed_reason.replace(/_/g, " ")}</p>}
          {score?.caps.map((c) => <p key={c} className="mt-2 rounded bg-breach/10 p-2 text-sm text-breach">Capped at F: {c}</p>)}
          {s.rig_saturation && <p className="mt-2 rounded bg-warn/10 p-2 text-sm text-warn">Rig saturated — {s.rig_saturation}</p>}
          <div className="mt-3 flex flex-wrap gap-1.5">{run.flags.map((f) => <Badge key={f} tone={f.includes("pricing") ? "muted" : "warn"}>{f.split(":")[0].replace(/_/g, " ")}</Badge>)}</div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs num">
            {Object.entries(outcomes).map(([k, v]) => <div key={k} className="rounded-xl bg-panel2/70 p-2"><div className="text-lg font-semibold">{v}</div><div className="text-muted">{k.replace(/_/g, " ")} calls</div></div>)}
          </div>
        </Panel>
        <Panel title="Sub-scores — every input and weight" pad={false} className="lg:col-span-2">
          {score?.subscores.map((sub) => <SubScoreRow key={sub.id} s={sub} />) ?? <p className="p-4 text-sm text-muted">Scoring runs when the last call terminates.</p>}
        </Panel>
      </div>
      <div className="mt-4">
        <Panel title="Metrics — breaches first" pad={false} actions={<EvidenceLabel kind="MEASURED" />}>
          <DataTable<MetricRow> rows={breachFirst} rowKey={(m) => m.name}
            rowClass={(m) => (passes(m.value, doc.metrics[m.name]?.threshold, doc.metrics[m.name]?.direction) === false ? "text-breach" : "")}
            columns={[
              { key: "n", header: "Metric", render: (m) => METRIC_LABELS[m.name] ?? m.name },
              { key: "v", header: "Value", align: "right", render: (m) => <b>{m.name.startsWith("est_") ? <>{fmt(m.value, m.unit)} <EvidenceLabel kind="ESTIMATED" /></> : fmt(m.value, m.unit)}</b> },
              { key: "t", header: "Threshold", align: "right", render: (m) => doc.metrics[m.name] ? <span className="text-muted">{doc.metrics[m.name].direction === "higher_is_better" ? "≥" : "≤"} {doc.metrics[m.name].threshold}{m.unit === "%" ? "%" : m.unit === "ms" ? " ms" : ""}</span> : <span className="text-muted">—</span> },
              { key: "s", header: "Status", render: (m) => { const p = passes(m.value, doc.metrics[m.name]?.threshold, doc.metrics[m.name]?.direction); return p === null ? <span className="text-muted">reported</span> : <Badge tone={p ? "pass" : "breach"}>{p ? "pass" : "breach"}</Badge>; } },
              { key: "c", header: "n", align: "right", render: (m) => m.n },
              { key: "f", header: "Flags", render: (m) => <span className="text-xs text-muted">{m.flags.join(", ")}</span> },
            ]} />
        </Panel>
      </div>
      {score?.epochs && score.epochs.length > 1 && (
        <div className="mt-4">
          <Panel title="By condition epoch (mid-run injection)" pad={false}>
            <DataTable rows={score.epochs} rowKey={(e) => String(e.epoch)} columns={[
              { key: "e", header: "Epoch", render: (e) => `${e.epoch} · ${run.epochs[e.epoch]?.profile ?? (e.epoch === 0 ? run.condition_profile_key : "custom")}` },
              { key: "p50", header: "Latency p50", align: "right", render: (e) => fmt(e.p50, "ms", 0) },
              { key: "p95", header: "Latency p95", align: "right", render: (e) => fmt(e.p95, "ms", 0) },
              { key: "n", header: "turns", align: "right", render: (e) => e.n },
            ]} />
          </Panel>
        </div>
      )}
      <div className="mt-4">
        <Panel title={`Calls — failures first · ${s.calls.length}`} pad={false}>
          <DataTable<Call> rows={s.calls} rowKey={(c) => c.id} onRowClick={(c) => nav(`/dashboard/calls/${c.id}`)} columns={[
            { key: "st", header: "Status", render: (c) => <Badge tone={c.status === "completed" ? "pass" : c.status === "errored" ? "breach" : c.status === "failed" || c.status === "needs_review" ? "warn" : "live"}>{c.status.replace("_", " ")}</Badge> },
            { key: "sc", header: "Scenario", render: (c) => <span className="mono text-xs">{c.scenario_key}</span> },
            { key: "pe", header: "Persona", render: (c) => <span className="text-xs">{c.persona_key}</span> },
            { key: "r", header: "Reason", render: (c) => <span className="mono text-xs text-muted">{c.reason_code ?? ""}</span> },
            { key: "d", header: "Duration", align: "right", render: (c) => dur(c.duration_ms) },
            { key: "t", header: "Talk-over", align: "right", render: (c) => fmt(c.talkover_ms, "ms", 0) },
            { key: "da", header: "Dead air", align: "right", render: (c) => fmt(c.dead_air_ratio, "%") },
            { key: "i", header: "Barge-in", align: "right", render: (c) => (c.interruptions ?? []).filter((i) => i.status === "applied").map((i) => i.no_yield ? "no-yield" : `${Math.round(i.barge_stop_ms ?? 0)}`).join(" · ") || "—" },
          ]} />
        </Panel>
      </div>
      <div className="mt-4"><Disclosure text={s.disclosure} calibration={s.calibration} /></div>
      <p className="mt-2 text-xs text-muted">{s.disclosures.task_success} {s.disclosures.reproducibility}</p>
    </>
  );
}
