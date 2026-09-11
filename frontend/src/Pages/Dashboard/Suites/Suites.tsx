import { ApiError } from "../../../api/client";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, DataTable, ErrorState, Panel, Skeleton, TextArea } from "../../../components/ui";
import { METRIC_LABELS } from "../../../components/ui/format";
import { useSuites } from "./useSuites";

const TAG_TONE = { happy_path: "pass", edge_case: "info", adversarial: "breach", out_of_scope: "warn" } as const;

export default function Suites() {
  const { suites, conditions, thresholds, selected, setSelected, yaml, setYaml, upload } = useSuites();
  if (suites.isLoading) return <Skeleton rows={6} />;
  if (suites.isError) return <ErrorState error={suites.error} retry={() => suites.refetch()} />;
  const suite = suites.data![0];
  const scen = suite?.scenarios.find((s) => s.key === selected) ?? suite?.scenarios[0];
  const thr = thresholds.data?.[0];
  const upErr = upload.error instanceof ApiError ? upload.error : null;
  return (
    <>
      <PageHeader title="Suites & conditions" subtitle={suite && <>Suite <b>{suite.name}</b> · <span className="mono">{suite.version_hash.slice(0, 16)}…</span> · scenarios are data, versioned by content hash</>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Scenarios" pad={false}>
          {suite?.scenarios.map((s) => (
            <button key={s.key} onClick={() => setSelected(s.key)}
              className={`flex w-full items-center justify-between gap-2 border-b border-line/60 px-4 py-2.5 text-left text-sm last:border-0 ${scen?.key === s.key ? "bg-panel2" : "hover:bg-panel2"}`}>
              <span className="mono text-xs">{s.key}</span>
              <Badge tone={TAG_TONE[s.coverage_tag]}>{s.coverage_tag.replace("_", " ")}</Badge>
            </button>
          ))}
        </Panel>
        {scen && (
          <Panel title={scen.key} className="lg:col-span-2">
            <p className="text-sm">{scen.description}</p>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <div>
                <div className="text-xs uppercase tracking-wider text-muted">Objective (given to the caller)</div>
                <p className="mt-1 text-sm">{scen.objective}</p>
                <div className="mt-3 text-xs uppercase tracking-wider text-muted">Opening line</div>
                <p className="mt-1 text-sm mono">"{scen.opening_utterance}"</p>
                <div className="mt-3 text-xs uppercase tracking-wider text-muted">Timing</div>
                <p className="mt-1 text-sm num">{scen.timing?.max_turns ?? 12} turns · {scen.timing?.max_duration_s ?? 120} s · turn timeout {scen.timing?.turn_timeout_ms ?? 8000} ms</p>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted">Goal checklist (given to the referee only)</div>
                <ol className="mt-1 list-decimal space-y-1 pl-4 text-sm">{scen.goal_checklist.map((g) => <li key={g.id}>{g.text}</li>)}</ol>
                <div className="mt-3 text-xs uppercase tracking-wider text-muted">Behaviour policies</div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {Object.entries(scen.behaviour_policies ?? {}).filter(([, v]) => v.enabled).map(([k, v]) => (
                    <Badge key={k} tone="info">{k} {v.pause_ms ? `${v.pause_ms} ms` : ""}</Badge>
                  ))}
                  {!Object.values(scen.behaviour_policies ?? {}).some((v) => v.enabled) && <span className="text-sm text-muted">none</span>}
                </div>
              </div>
            </div>
          </Panel>
        )}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Personas" pad={false}>
          <DataTable rows={suite?.personas ?? []} rowKey={(p) => p.key} columns={[
            { key: "k", header: "Persona", render: (p) => <span className="mono text-xs">{p.key}</span> },
            { key: "r", header: "Rate", render: (p) => `${p.speech_rate}×`, align: "right" },
            { key: "p", header: "Patience", render: (p) => `${p.patience_s} s`, align: "right" },
            { key: "i", header: "Interrupts", render: (p) => p.interruption_tendency ?? 0, align: "right" },
            { key: "v", header: "Verbosity", render: (p) => p.verbosity },
          ]} />
        </Panel>
        <Panel title="Condition profiles — every parameter" pad={false}>
          <DataTable rows={conditions.data ?? []} rowKey={(c) => c.key} columns={[
            { key: "k", header: "Profile", render: (c) => <span className="mono text-xs">{c.key}</span> },
            { key: "p", header: "Parameters", render: (c) => Object.keys(c.parameters).length ? (
              <div className="space-y-0.5 text-xs mono">{Object.entries(c.parameters).map(([k, v]) => <div key={k}><span className="text-muted">{k}</span> {JSON.stringify(v)}</div>)}</div>
            ) : <span className="text-xs text-muted">none (baseline)</span> },
          ]} />
        </Panel>
      </div>
      {thr && (
        <div className="mt-4">
          <Panel title={`Threshold profile "${thr.key}" · ${thr.version_hash.slice(0, 12)}`} pad={false}>
            <DataTable rows={Object.entries(thr.document.metrics)} rowKey={([k]) => k} columns={[
              { key: "m", header: "Metric", render: ([k]) => METRIC_LABELS[k] ?? k },
              { key: "i", header: "Ideal → 100", render: ([, b]) => `${b.ideal} ${b.unit ?? ""}`, align: "right" },
              { key: "t", header: "Threshold → 70", render: ([, b]) => <b>{b.threshold} {b.unit ?? ""}</b>, align: "right" },
              { key: "l", header: "Limit → 0", render: ([, b]) => `${b.limit} ${b.unit ?? ""}`, align: "right" },
              { key: "d", header: "Direction", render: ([, b]) => b.direction.replace(/_/g, " ") },
            ]} />
            <p className="px-4 py-2 text-xs text-muted">At exactly the threshold a metric scores 70 — the bottom of grade C. Hard breaches: {Object.entries(thr.document.hard_breaches).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}.</p>
          </Panel>
        </div>
      )}
      <div className="mt-4">
        <Panel title="Upload a suite version (YAML)">
          <TextArea rows={8} value={yaml} onChange={(e) => setYaml(e.target.value)} placeholder="key: my-suite&#10;scenarios: [...]&#10;personas: [...]" />
          <div className="mt-2 flex items-center gap-3">
            <Button variant="primary" busy={upload.isPending} disabled={!yaml.trim()} onClick={() => upload.mutate()}>Validate & save</Button>
            {upload.data && <Badge tone="pass">saved · {upload.data.version_hash.slice(0, 12)}</Badge>}
            {upErr && <span className="text-sm text-breach">{upErr.message}{upErr.body?.line ? ` (line ${upErr.body.line}, column ${upErr.body.column})` : ""}</span>}
          </div>
        </Panel>
      </div>
    </>
  );
}
