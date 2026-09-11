import type { ReportData } from "../api/types";
import { EvidenceLabel } from "./EvidenceLabel";
import { GradeChip } from "./GradeChip";
import { Badge, DataTable, Panel } from "./ui";
import { fmt } from "./ui/format";

/** The report as it leaves the tool (S8). Used by the private report page and the public share link.
 *  The limitations section is always rendered and cannot be collapsed (SRS-FR-110). */
export function ReportView({ r }: { r: ReportData }) {
  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-center gap-4">
          <GradeChip grade={r.grade} size="lg" reason={r.suppressed_reason} />
          <div className="min-w-0 flex-1">
            <div className="text-lg font-semibold">{r.target}</div>
            <div className="text-xs text-muted mono">run {r.run_id} · {r.status}</div>
            {r.suppressed_reason && <div className="mt-1 text-sm text-warn">No grade emitted — {r.suppressed_reason.replace(/_/g, " ")}</div>}
            {r.caps.map((c) => <div key={c} className="mt-1 text-sm text-breach">Capped at F: {c}</div>)}
          </div>
          <div className="text-4xl font-bold num">{fmt(r.overall, "", 2)}</div>
        </div>
      </Panel>
      <Panel title="Metrics" pad={false}>
        <DataTable rows={r.metrics} rowKey={(m) => m.name} rowClass={(m) => (m.status === "breach" ? "text-breach" : "")} columns={[
          { key: "m", header: "Metric", render: (m) => <span title={m.definition}>{m.met_id} {m.label}</span> },
          { key: "v", header: "Value", align: "right", render: (m) => <b>{fmt(m.value, m.unit)}</b> },
          { key: "t", header: "Threshold", align: "right", render: (m) => m.threshold != null ? <span className="text-muted">{m.threshold} <EvidenceLabel kind="THRESHOLD" /></span> : "—" },
          { key: "s", header: "Status", render: (m) => m.status ? <Badge tone={m.status === "pass" ? "pass" : "breach"}>{m.status}</Badge> : "" },
          { key: "n", header: "n", align: "right", render: (m) => m.n },
          { key: "e", header: "Evidence", render: (m) => <EvidenceLabel kind={m.evidence} /> },
        ]} />
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Configuration">
          <dl className="grid grid-cols-3 gap-y-1.5 text-sm">
            <dt className="text-muted">Suite</dt><dd className="col-span-2">{r.suite.name} <span className="mono text-xs">{r.suite.version_hash.slice(0, 16)}…</span></dd>
            <dt className="text-muted">Seed</dt><dd className="col-span-2 mono">{r.seed}</dd>
            <dt className="text-muted">Conditions</dt><dd className="col-span-2"><span className="mono">{r.conditions.profile}</span> <span className="mono text-xs text-muted">{JSON.stringify(r.conditions.parameters)}</span></dd>
            <dt className="text-muted">Thresholds</dt><dd className="col-span-2 mono">{r.thresholds.profile}@{r.thresholds.version_hash.slice(0, 12)}</dd>
            <dt className="text-muted">Concurrency</dt><dd className="col-span-2 num">requested {r.concurrency.requested} · measured peak {r.concurrency.peak_measured ?? "—"}</dd>
            <dt className="text-muted">Rig cost</dt><dd className="col-span-2 num">{fmt(r.cost.rig_usd, "USD")} <EvidenceLabel kind="MEASURED" /> {r.cost.pricing_flags.map((f) => <Badge key={f}>{f}</Badge>)}</dd>
            {r.cost.estimated_target_usd != null && <><dt className="text-muted">Target cost</dt><dd className="col-span-2 num">{fmt(r.cost.estimated_target_usd, "USD")} <EvidenceLabel kind="ESTIMATED" /></dd></>}
          </dl>
        </Panel>
        <Panel title="Methodology & calibration">
          <ul className="space-y-1.5 text-sm">{Object.values(r.methodology).map((m) => <li key={m}>{m}</li>)}</ul>
          {r.calibration ? (
            <p className="mt-3 text-sm">Error bound <b className="num">{r.calibration.bound_ms} ms</b> <EvidenceLabel kind="MEASURED" /> over {r.calibration.n} loopback repetitions, commit <span className="mono">{r.calibration.git_sha?.slice(0, 8)}</span>. <span className="text-muted">{r.calibration.scope}</span></p>
          ) : <p className="mt-3 text-sm text-muted">No calibration artefact available.</p>}
        </Panel>
      </div>
      <section className="rounded-lg border border-line bg-panel2 p-4" aria-label="Limitations">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">Limitations</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </section>
    </div>
  );
}
