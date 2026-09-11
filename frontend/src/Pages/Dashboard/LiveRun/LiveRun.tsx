import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Disclosure } from "../../../components/Disclosure";
import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { RunStatus } from "../../../components/RunStatus";
import { Badge, Button, ErrorState, Panel, Skeleton } from "../../../components/ui";
import { dur, fmt, short } from "../../../components/ui/format";
import { useLiveRun, type Tile } from "./useLiveRun";

const STATUS_COLOR: Record<string, string> = {
  pending: "border-line", dialling: "border-info", connected: "border-live", in_call: "border-live", scoring: "border-info",
  completed: "border-pass", failed: "border-warn", needs_review: "border-warn", errored: "border-breach",
};

function Bars({ values, threshold }: { values: (number | null)[]; threshold: number }) {
  const max = Math.max(threshold * 1.4, ...values.map((v) => v ?? 0));
  return (
    <svg viewBox={`0 0 ${Math.max(10, values.length * 6)} 24`} className="h-6 w-full" preserveAspectRatio="none" aria-hidden>
      <line x1="0" x2="100%" y1={24 - (threshold / max) * 24} y2={24 - (threshold / max) * 24} stroke="var(--color-breach)" strokeWidth="0.5" strokeDasharray="2 2" />
      {values.map((v, i) => v == null
        ? <rect key={i} x={i * 6 + 1} y={20} width={4} height={4} fill="var(--color-muted)" />
        : <rect key={i} x={i * 6 + 1} y={24 - (v / max) * 24} width={4} height={(v / max) * 24} fill={v > threshold ? "var(--color-breach)" : "var(--color-live)"} />)}
    </svg>
  );
}

function CallTile({ t, threshold }: { t: Tile; threshold: number }) {
  const inCall = t.status === "in_call" || t.status === "dialling";
  const done = ["completed", "failed", "needs_review", "errored"].includes(t.status);
  const body = (
    <div className={`rounded-md border-2 bg-panel p-2 ${STATUS_COLOR[t.status] ?? "border-line"}`}>
      <div className="flex items-center justify-between gap-1">
        <span className="truncate text-[11px] mono">{t.scenario}</span>
        {inCall && <span className="pulse h-2 w-2 shrink-0 rounded-full bg-live" aria-label="in call" />}
      </div>
      <div className="truncate text-[11px] text-muted">{t.persona}</div>
      <Bars values={t.latencies} threshold={threshold} />
      <div className="flex items-center justify-between text-[11px] num">
        <span>{fmt(t.lastLatency, "ms", 0)}</span>
        <span className={t.status === "errored" ? "text-breach" : "text-muted"}>{t.status === "errored" ? t.reason ?? "errored" : t.status.replace("_", " ")}</span>
      </div>
    </div>
  );
  return done ? <Link to={`/dashboard/calls/${t.id}`} className="no-underline">{body}</Link> : body;
}

function Sparkline({ data, threshold }: { data: { p95: number; epoch: number }[]; threshold: number }) {
  const w = 300, h = 90;
  const max = Math.max(threshold * 1.3, ...data.map((d) => d.p95));
  const x = (i: number) => (data.length <= 1 ? 0 : (i / (data.length - 1)) * w);
  const y = (v: number) => h - (v / max) * h;
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.p95).toFixed(1)}`).join(" ");
  const dividers = data.map((d, i) => (i > 0 && d.epoch !== data[i - 1].epoch ? i : -1)).filter((i) => i > 0);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-24 w-full" role="img" aria-label="rolling p95 response latency">
      <line x1="0" x2={w} y1={y(threshold)} y2={y(threshold)} stroke="var(--color-breach)" strokeDasharray="4 3" strokeWidth="1" />
      <text x={w - 2} y={y(threshold) - 3} textAnchor="end" fontSize="9" fill="var(--color-breach)">threshold {threshold} ms</text>
      {dividers.map((i) => <line key={i} x1={x(i)} x2={x(i)} y1="0" y2={h} stroke="var(--color-warn)" strokeWidth="1" />)}
      <path d={path} fill="none" stroke="var(--color-live)" strokeWidth="2" />
    </svg>
  );
}

export default function LiveRun() {
  const L = useLiveRun();
  const s = L.summary.data;
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const threshold = s?.threshold_document.metrics.response_latency_p95?.threshold ?? 1500;
  const current = L.rolling.at(-1)?.p95 ?? null;
  const breaching = current != null && current > threshold;
  const prevBreach = useRef(false);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (breaching && !prevBreach.current) { setFlash(true); setTimeout(() => setFlash(false), 1300); }
    prevBreach.current = breaching;
  }, [breaching]);
  if (L.summary.isLoading) return <Skeleton rows={8} />;
  if (L.summary.isError) return <ErrorState error={L.summary.error} retry={() => L.summary.refetch()} />;
  const run = s!.run;
  const inflight = run.status === "queued" || run.status === "running";
  const elapsed = run.started_at ? ((run.ended_at ? new Date(run.ended_at).getTime() : now) - new Date(run.started_at).getTime()) : 0;
  const p = L.progress;
  const done = (p.completed ?? 0) + (p.failed ?? 0) + (p.errored ?? 0) + (p.needs_review ?? 0);
  const spend = L.spend ?? s!.live.spend_usd ?? run.rig_cost_usd ?? 0;
  const epoch = L.epochs.at(-1);
  const activeProfile = epoch?.profile ?? (epoch && epoch.epoch > 0 ? "custom" : run.condition_profile_key);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-line bg-panel px-4 py-3 num">
        <div className="flex items-center gap-2">
          <EvidenceLabel kind={L.mode === "REPLAY" ? "REPLAY" : "LIVE"} />
          <span className="mono text-xs text-muted" title={run.id}>run {short(run.id)}</span>
          <RunStatus run={run} />
        </div>
        <div className="text-xs"><span className="text-muted">seed</span> <span className="mono">{run.seed}</span></div>
        <div className="text-xs"><span className="text-muted">target</span> {s!.target?.name}</div>
        <div className="text-xs"><span className="text-muted">elapsed</span> {dur(elapsed)}</div>
        <div className="text-xs"><span className="text-muted">calls</span> <b>{done}</b>/{run.total_calls}</div>
        <div className="text-xs"><span className="text-muted">active</span> <b>{p.active ?? s!.live.active ?? 0}</b> · <span className="text-muted">peak measured</span> <b>{p.peak ?? run.concurrency_peak ?? 0}</b></div>
        <div className="text-xs"><span className="text-muted">rig spend</span> {fmt(spend, "USD")} / {fmt(run.spend_cap_usd, "USD")}</div>
        <div className="ml-auto flex items-center gap-2">
          {L.conn === "reconnecting" && inflight && <Badge tone="warn">reconnecting…</Badge>}
          {inflight && L.mode === "LIVE" && <Button variant="danger" busy={L.abort.isPending} onClick={() => L.abort.mutate()}>Abort</Button>}
          {!inflight && <Link to={`/dashboard/runs/${run.id}`}><Button variant="primary">Results</Button></Link>}
        </div>
      </div>
      <p className="mb-3 text-xs text-muted lg:hidden">The live view is desktop-first; tiles wrap on narrow screens.</p>
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-3">
          <Panel title={`Calls · ${L.tiles.length}`}>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
              {L.tiles.map((t) => <CallTile key={t.id} t={t} threshold={threshold} />)}
            </div>
          </Panel>
        </div>
        <div className="space-y-4">
          <Panel title="Condition control">
            <div className="text-xs text-muted">Active profile · epoch {epoch?.epoch ?? 0}</div>
            <div className="mb-3 text-lg font-semibold">{activeProfile}</div>
            <div className="grid grid-cols-2 gap-2">
              {(L.conditions.data ?? []).map((c) => (
                <button key={c.key} disabled={!inflight || L.mode !== "LIVE" || L.inject.isPending || c.key === activeProfile}
                  onClick={() => L.inject.mutate(c.key)}
                  className={`rounded-md border px-2 py-2 text-sm font-medium transition disabled:opacity-40 ${c.key === activeProfile ? "border-live bg-live/10 text-live" : c.key === "clean" ? "border-line hover:border-pass" : "border-warn/60 text-warn hover:bg-warn/10"}`}>
                  {c.key === "clean" ? "↺ clean" : `⚡ ${c.key}`}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted">Calls adopt a change at their next turn boundary, so no turn is measured under two regimes.</p>
          </Panel>
          <Panel title="Rolling p95 response latency">
            <div className={`rounded ${flash ? "flash" : ""}`}>
              <div className={`text-3xl font-bold num ${breaching ? "text-breach" : "text-fg"}`}>{fmt(current, "ms", 0)}</div>
              <div className="text-xs text-muted">last 20 turns · threshold {threshold} ms {breaching && <Badge tone="breach">breaching</Badge>}</div>
            </div>
            <Sparkline data={L.rolling} threshold={threshold} />
            <div className="mt-1 space-y-0.5 text-xs num">
              {L.byEpoch.map((e) => <div key={e.epoch} className="flex justify-between"><span className="text-muted">epoch {e.epoch}</span><span>p95 {fmt(e.p95, "ms", 0)} · n={e.n}</span></div>)}
            </div>
          </Panel>
          <Panel title="Interruptions">
            {L.barges.length === 0 ? <p className="text-xs text-muted">No barge-in measured yet.</p> : (
              <div className="max-h-48 space-y-1 overflow-y-auto text-xs num">
                {L.barges.map((b, i) => (
                  <div key={i} className="flex justify-between"><span className="mono text-muted">{short(b.call, 6)} t{b.turn}</span>
                    <span className={b.noYield ? "text-breach" : b.ms > 800 ? "text-warn" : "text-pass"}>{b.noYield ? "no yield (≥2000 ms)" : `${fmt(b.ms, "ms", 0)} to stop`}</span></div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </div>
      <div className="mt-4"><Disclosure text={s!.disclosure} calibration={s!.calibration} /></div>
    </>
  );
}
