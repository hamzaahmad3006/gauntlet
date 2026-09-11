import { useState } from "react";
import { API_BASE } from "../../../api/client";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, DataTable, EmptyState, Field, Input, Panel, Select, TextArea } from "../../../components/ui";
import { ago, short } from "../../../components/ui/format";
import { useIntegrations } from "./useIntegrations";

function workflow(targetId: string) {
  return `# .github/workflows/gauntlet.yml
name: gauntlet-gate
on:
  pull_request:
    paths: ["agent/**", "prompts/**", "gauntlet.yaml"]
permissions:
  contents: read
  pull-requests: write
jobs:
  voice-regression:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: hamzaahmad3006/gauntlet/.github/actions/gauntlet-gate@main
        with:
          config: gauntlet.yaml
          api-key: \${{ secrets.GAUNTLET_API_KEY }}

# gauntlet.yaml — committed, contains no secrets
api_url: ${API_BASE}
target_id: ${targetId || "<target id>"}
suite: booking-core
conditions: mobile
thresholds: default
concurrency: 6
repeats: 1
spend_cap_usd: 1.50
gate:
  tolerance_points: 3`;
}

export default function Integrations() {
  const I = useIntegrations();
  const [target, setTarget] = useState("");
  const tid = target || I.targets.data?.[0]?.id || "";
  return (
    <>
      <PageHeader title="CI gate" subtitle="Move GAUNTLET into the pipeline: a scoped key, a baseline, and a check that fails when turn-taking regresses." />
      {I.fresh && (
        <div className="mb-4 rounded-lg border border-pass/50 bg-pass/5 p-4">
          <div className="text-sm font-semibold">Copy this key now — it will not be shown again.</div>
          <div className="mt-2 flex gap-2"><Input readOnly value={I.fresh} className="mono" /><Button onClick={() => navigator.clipboard?.writeText(I.fresh!)}>Copy</Button><Button variant="ghost" onClick={I.dismiss}>Done</Button></div>
          <p className="mt-2 text-xs text-muted">Store it as the repository secret GAUNTLET_API_KEY. It can create runs, read them and evaluate gates — never create keys, targets or thresholds.</p>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="API keys" actions={
          <div className="flex gap-2"><Input value={I.name} onChange={(e) => I.setName(e.target.value)} className="w-40" /><Button variant="primary" busy={I.create.isPending} onClick={() => I.create.mutate()}>Create key</Button></div>}>
          {I.keys.data?.length ? (
            <DataTable rows={I.keys.data} rowKey={(k) => k.id} columns={[
              { key: "n", header: "Name", render: (k) => k.name },
              { key: "p", header: "Prefix", render: (k) => <span className="mono text-xs">{k.prefix}…</span> },
              { key: "s", header: "Scopes", render: (k) => <span className="flex flex-wrap gap-1">{k.scopes.map((s) => <Badge key={s}>{s}</Badge>)}</span> },
              { key: "u", header: "Last used", render: (k) => <span className="text-xs text-muted">{k.last_used_at ? ago(k.last_used_at) : "never"}</span> },
              { key: "r", header: "", render: (k) => k.revoked_at ? <Badge tone="muted">revoked</Badge> : <Button variant="danger" onClick={() => I.revoke.mutate(k.id)}>Revoke</Button> },
            ]} />
          ) : <EmptyState title="No keys yet">Create one key for your CI. The gate runs the suite on every pull request, compares against the target's baseline and fails the check on a breach.</EmptyState>}
        </Panel>
        <Panel title="Workflow — copy into your repository">
          <Field label="Target"><Select value={tid} onChange={(e) => setTarget(e.target.value)}>{I.targets.data?.map((t) => <option key={t.id} value={t.id}>{t.name}{t.baseline_run_id ? " (baseline set)" : " (no baseline)"}</option>)}</Select></Field>
          <TextArea rows={16} readOnly value={workflow(tid)} className="mt-2" />
          <p className="mt-2 text-xs text-muted">Exit codes: 0 pass · 2 genuine metric breach · 3 ungatable run · 4 infrastructure error — so a pipeline can tell a regression from an outage.</p>
        </Panel>
      </div>
      <div className="mt-4">
        <Panel title="Recent gate results" pad={false}>
          {I.gates.data?.length ? (
            <DataTable rows={I.gates.data} rowKey={(g) => g.id} columns={[
              { key: "v", header: "Verdict", render: (g) => <Badge tone={g.verdict === "passed" ? "pass" : "breach"}>{g.verdict}</Badge> },
              { key: "r", header: "Candidate", render: (g) => <a className="mono text-xs underline" href={`/dashboard/runs/${g.run_id}`}>{short(g.run_id)}</a> },
              { key: "b", header: "Baseline", render: (g) => <a className="mono text-xs underline" href={`/dashboard/runs/${g.baseline_run_id}`}>{short(g.baseline_run_id)}</a> },
              { key: "x", header: "Breaches", render: (g) => <span className="text-xs">{g.breaches.map((x) => `${x.metric} ${x.delta != null ? (x.delta > 0 ? "+" : "") + Math.round(x.delta * 100) / 100 : ""}`).join(" · ") || "—"}</span> },
              { key: "t", header: "When", render: (g) => <span className="text-xs text-muted">{ago(g.created_at)}</span> },
            ]} />
          ) : <div className="p-4"><EmptyState title="No gate evaluated yet">Promote a run to baseline on its results page, then run the action (or `gauntlet ci`) on a pull request.</EmptyState></div>}
        </Panel>
      </div>
    </>
  );
}
