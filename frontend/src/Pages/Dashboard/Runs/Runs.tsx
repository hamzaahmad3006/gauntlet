import { useNavigate } from "react-router-dom";
import type { Run } from "../../../api/types";
import { GradeChip } from "../../../components/GradeChip";
import { PageHeader } from "../../../components/Layout";
import { RunStatus } from "../../../components/RunStatus";
import { Badge, Button, DataTable, EmptyState, ErrorState, Field, Panel, Select, Skeleton } from "../../../components/ui";
import { ago, fmt, humanize, short } from "../../../components/ui/format";
import { useRuns } from "./useRuns";

export default function Runs() {
  const R = useRuns();
  const nav = useNavigate();
  return (
    <>
      <PageHeader eyebrow="History" title="Run history" subtitle="Newest first. Every run keeps its seed, suite hash and threshold version, so any of them can be replayed or compared." actions={<Button variant="primary" onClick={() => nav("/dashboard/runs/new")}>New run</Button>} />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-64"><Field label="Target"><Select id="runs-target" value={R.target} onChange={(e) => R.setTarget(e.target.value)}><option value="">All targets</option>{R.targets.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field></div>
        <div className="w-44"><Field label="Status"><Select id="runs-status" value={R.status} onChange={(e) => R.setStatus(e.target.value)}><option value="">Any status</option>{["queued", "running", "completed", "aborted", "aborted_budget", "failed"].map((st) => <option key={st} value={st}>{st.replace(/_/g, " ")}</option>)}</Select></Field></div>
      </div>
      <Panel pad={false} title="Runs">
        {R.runs.isLoading ? <div className="p-4"><Skeleton rows={5} /></div>
          : R.runs.isError ? <div className="p-4"><ErrorState error={R.runs.error} retry={() => R.runs.refetch()} /></div>
          : (
            <DataTable<Run> rows={R.items} rowKey={(r) => r.id} onRowClick={(r) => nav(r.status === "running" || r.status === "queued" ? `/dashboard/runs/${r.id}/live` : `/dashboard/runs/${r.id}`)}
              empty={<div className="p-4"><EmptyState title="No runs match">Start one from a target.</EmptyState></div>}
              columns={[
                { key: "g", header: "Grade", render: (r) => <GradeChip grade={r.grade} size="sm" /> },
                { key: "t", header: "Target", render: (r) => <span>{r.target_name}<span className="block mono text-[11px] text-muted">{short(r.id)}</span></span> },
                { key: "c", header: "Conditions", render: (r) => <span><span className="font-medium">{humanize(r.condition_profile_key)}</span>{r.label && <span className="block text-[11px] text-muted">{r.label}</span>}</span> },
                { key: "n", header: "Calls", align: "right", render: (r) => r.total_calls },
                { key: "p", header: "Peak conc.", align: "right", render: (r) => r.concurrency_peak ?? "—" },
                { key: "o", header: "Score", align: "right", render: (r) => <span className="font-semibold">{fmt(r.overall, "", 1)}</span> },
                { key: "f", header: "Notes", render: (r) => { const fl = r.flags.filter((f) => !f.includes(":") && f !== "pricing_not_configured" && f !== "partial_scoring"); return fl.length ? <span className="flex items-center gap-1" title={fl.map((f) => f.replace(/_/g, " ")).join(", ")}><Badge tone={fl.includes("insufficient_sample") ? "warn" : "muted"}>{fl[0].replace(/_/g, " ")}</Badge>{fl.length > 1 && <span className="text-[11px] text-muted">+{fl.length - 1}</span>}</span> : <span className="text-xs text-muted">—</span>; } },
                { key: "s", header: "Status", render: (r) => <RunStatus run={r} /> },
                { key: "w", header: "When", render: (r) => <span className="whitespace-nowrap text-xs text-muted">{ago(r.created_at)}</span> },
              ]} />
          )}
        {R.runs.hasNextPage && <div className="p-3 text-center"><Button busy={R.runs.isFetchingNextPage} onClick={() => R.runs.fetchNextPage()}>Load more</Button></div>}
      </Panel>
    </>
  );
}
