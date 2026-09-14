import { Link, useNavigate } from "react-router-dom";
import type { Target } from "../../../api/types";
import { GradeChip } from "../../../components/GradeChip";
import { PageHeader } from "../../../components/Layout";
import { RunStatus } from "../../../components/RunStatus";
import { SystemBadge } from "../../../components/SystemBadge";
import { Badge, Button, EmptyState, ErrorState, Panel, Skeleton } from "../../../components/ui";
import { ago, fmt, humanize } from "../../../components/ui/format";
import { useTargets } from "./useTargets";

const QUICK = [
  { to: "/dashboard/talk", title: "Talk to the agent", text: "Call the bundled restaurant agent from your browser and hear how fast it answers.", cta: "Start a call", tone: "from-emerald-500 to-teal-500", icon: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm7 9a7 7 0 0 1-14 0m7 7v3" },
  { to: "/dashboard/runs/new", title: "Watch a synthetic call", text: "An AI caller phones the agent while you watch the conversation and the latency live.", cta: "Run a 1-call demo", tone: "from-cyan-500 to-sky-500", icon: "M5 3l14 9-14 9V3Z" },
  { to: "/dashboard/compare", title: "Compare tuned vs slow", text: "Two tunings of the same agent on the same network: grade A against grade C.", cta: "Open the comparison", tone: "from-violet-500 to-fuchsia-500", icon: "M8 3v18M16 3v18M3 8h5M16 16h5" },
];

function TargetRow({ t }: { t: Target }) {
  const nav = useNavigate();
  const r = t.last_run;
  const h = r?.headline ?? {};
  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-line/60 px-4 py-3 last:border-0">
      <GradeChip grade={r?.grade ?? null} reason={r ? `last run ${r.status}` : "no run yet"} />
      <div className="min-w-[220px] flex-1">
        <Link to={`/dashboard/targets/${t.id}`} className="font-medium no-underline hover:underline">{t.name}</Link>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          <Badge>{t.adapter === "websocket_pcm" ? "WebSocket PCM" : "LiveKit"}</Badge>
          {t.bundled && <Badge tone="info" title="Bundled test fixture, not a product">fixture</Badge>}
          {!t.verified_at && <Badge tone="warn">unverified</Badge>}
          {t.baseline_run_id && <Badge tone="pass">baseline set</Badge>}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-6 text-right num">
        <div><div className="text-[11px] uppercase text-muted">Latency p95</div><div className="font-semibold">{fmt(h.response_latency_p95, "ms", 0)}</div></div>
        <div><div className="text-[11px] uppercase text-muted">Barge-in p95</div><div className="font-semibold">{fmt(h.barge_in_stop_p95, "ms", 0)}</div></div>
        <div><div className="text-[11px] uppercase text-muted">Cost / success</div><div className="font-semibold">{t.cost_model_declared ? fmt(h.est_cost_per_successful_session, "USD") : <span className="text-xs font-normal text-muted">not declared</span>}</div></div>
      </div>
      <div className="flex w-full items-center justify-end gap-2 sm:w-auto">
        {r && <span className="text-xs text-muted">{ago(r.created_at)}</span>}
        {r && <RunStatus run={r} />}
        <Button variant="primary" onClick={() => nav(`/dashboard/runs/new?target=${t.id}`)} disabled={!t.verified_at}>Run suite</Button>
      </div>
    </div>
  );
}

export default function Targets() {
  const { targets, recent } = useTargets();
  return (
    <>
      <PageHeader eyebrow="Workspace" title="Agents under test" subtitle="Every voice agent you test, its last grade and its headline numbers. Failures sort first."
        actions={<Link to="/dashboard/targets/new"><Button>+ Connect your agent</Button></Link>} />
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        {QUICK.map((q, i) => (
          <Link key={q.to} to={q.to} className="glass lift group relative overflow-clip rounded-2xl p-5 no-underline float-in" style={{ animationDelay: `${i * 0.06}s` }}>
            <div className={`absolute -right-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br ${q.tone} opacity-15 blur-2xl transition group-hover:opacity-30`} aria-hidden />
            <div className={`grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br ${q.tone} text-white shadow-md`}>
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={q.icon} /></svg>
            </div>
            <div className="mt-4 font-semibold">{q.title}</div>
            <p className="mt-1 text-sm text-muted">{q.text}</p>
            <div className="mt-3 text-sm font-semibold text-live">{q.cta} <span className="inline-block transition group-hover:translate-x-1">→</span></div>
          </Link>
        ))}
      </div>
      <div className="mb-3 flex justify-end"><SystemBadge detailed /></div>
      <Panel pad={false} title="Agents under test">
        {targets.isLoading ? <div className="p-4"><Skeleton rows={3} /></div>
          : targets.isError ? <div className="p-4"><ErrorState error={targets.error} retry={() => targets.refetch()} /></div>
          : targets.data!.length === 0 ? <div className="p-4"><EmptyState title="No targets">Seeding failed — sign out and in again to re-seed.</EmptyState></div>
          : targets.data!.map((t) => <TargetRow key={t.id} t={t} />)}
      </Panel>
      <div className="mt-6">
        <Panel title="Recent runs" actions={<Link to="/dashboard/runs" className="text-xs text-muted">All runs</Link>} pad={false}>
          {recent.data?.items.length ? (
            <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-3">
              {recent.data.items.map((r) => (
                <Link key={r.id} to={r.status === "running" || r.status === "queued" ? `/dashboard/runs/${r.id}/live` : `/dashboard/runs/${r.id}`}
                  className="flex items-center gap-3 bg-panel p-3 no-underline hover:bg-panel2">
                  <GradeChip grade={r.grade} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{r.target_name}</div>
                    <div className="text-xs text-muted">{humanize(r.condition_profile_key)} · {r.total_calls} calls · {ago(r.created_at)}</div>
                  </div>
                  <RunStatus run={r} />
                </Link>
              ))}
            </div>
          ) : <div className="p-4"><EmptyState title="No runs yet">Pick a target above and press <b>Run suite</b> — the bundled synthetic agent needs no setup.</EmptyState></div>}
        </Panel>
      </div>
    </>
  );
}
