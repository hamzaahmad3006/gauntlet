import { useNavigate } from "react-router-dom";
import type { Run } from "../../../api/types";
import { GradeChip } from "../../../components/GradeChip";
import { PageHeader } from "../../../components/Layout";
import { RunStatus } from "../../../components/RunStatus";
import { Badge, Button, DataTable, EmptyState, ErrorState, Field, Panel, Select, Skeleton } from "../../../components/ui";
import { ago, fmt, short } from "../../../components/ui/format";
import { useRuns } from "./useRuns";

export default function Runs() {
  const R = useRuns();
  const nav = useNavigate();
  return (
    <>
      <PageHeader title="Run history" subtitle="Newest first. Every run keeps its seed, suite hash and threshold version." actions={<Button variant="primary" onClick={() => nav("/dashboard/runs/new")}>New run</Button>} />
      <Panel pad={false} title={
        <div className="flex gap-3 normal-case tracking-normal">
          <Field label="Target"><Select value={R.target} onChange={(e) => R.setTarget(e.target.value)}><option value="">all</option>{R.targets.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
          <Field label="Status"><Select value={R.status} onChange={(e) => R.setStatus(e.target.value)}><option value="">all</option>{["queued", "running", "completed", "aborted", "aborted_budget", "failed"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
        </div>}>
        {R.runs.isLoading ? <div className="p-4"><Skeleton rows={5} /></div>
          : R.runs.isError ? <div className="p-4"><ErrorState error={R.runs.error} retry={() => R.runs.refetch()} /></div>
          : (
            <DataTable<Run> rows={R.items} rowKey={(r) => r.id} onRowClick={(r) => nav(r.status === "running" || r.status === "queued" ? `/dashboard/runs/${r.id}/live` : `/dashboard/runs/${r.id}`)}
              empty={<div className="p-4"><EmptyState title="No runs match">Start one from a target.</EmptyState></div>}
              columns={[
                { key: "g", header: "Grade", render: (r) => <GradeChip grade={r.grade} size="sm" /> },
                { key: "t", header: "Target", render: (r) => <span>{r.target_name}<span className="block mono text-[11px] text-muted">{short(r.id)}</span></span> },
                { key: "c", header: "Conditions", render: (r) => <span>{r.condition_profile_key}{r.label && <span className="block text-[11px] text-muted">{r.label}</span>}</span> },
                { key: "n", header: "Calls", align: "right", render: (r) => r.total_calls },
                { key: "p", header: "Peak conc.", align: "right", render: (r) => r.concurrency_peak ?? "—" },
                { key: "o", header: "Score", align: "right", render: (r) => fmt(r.overall, "", 1) },
                { key: "f", header: "Flags", render: (r) => <span className="flex flex-wrap gap-1">{r.flags.filter((f) => !f.includes(":") && f !== "pricing_not_configured").slice(0, 3).map((f) => <Badge key={f}>{f.replace(/_/g, " ")}</Badge>)}</span> },
                { key: "s", header: "Status", render: (r) => <RunStatus run={r} /> },
                { key: "w", header: "When", render: (r) => <span className="text-xs text-muted">{ago(r.created_at)}</span> },
              ]} />
          )}
        {R.runs.hasNextPage && <div className="p-3 text-center"><Button busy={R.runs.isFetchingNextPage} onClick={() => R.runs.fetchNextPage()}>Load more</Button></div>}
      </Panel>
    </>
  );
}
