import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { PageHeader } from "../../../components/Layout";
import { Badge, DataTable, EmptyState, ErrorState, Panel, Skeleton, Stat } from "../../../components/ui";
import { fmt } from "../../../components/ui/format";
import { useCalibration } from "./useCalibration";

/** One bar against the acceptable maximum: the headline is how little of the budget the rig uses. */
function ErrorBudget({ bound, max }: { bound: number; max: number }) {
  const pct = Math.min(100, (bound / max) * 100);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-extrabold tracking-tight text-pass num">{fmt(bound, "ms", 3)}</span>
        <span className="text-sm text-muted">of {fmt(max, "ms", 0)} allowed · {fmt(pct, "%", 1)} used</span>
      </div>
      <div className="relative mt-4 h-3 rounded-full bg-panel2" title={`${bound} ms measured, ${max} ms acceptable maximum`}>
        <div className="h-full rounded-full bg-pass" style={{ width: `${Math.max(pct, 1)}%` }} />
        <div className="absolute inset-y-[-4px] right-0 w-0.5 rounded bg-breach" aria-hidden />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-muted num"><span>0 ms</span><span className="text-breach">{fmt(max, "ms", 0)} acceptable max (THRESHOLD)</span></div>
      <p className="mt-3 text-xs text-muted">A latency the rig reports can be off by at most this much on a loopback path, which is small next to the 1,500 ms p95 threshold it judges agents against.</p>
    </div>
  );
}

/** Max |error| per programmed delay on one shared scale; a single series, so the title names it. */
function DelayBars({ levels }: { levels: { delay: string; max: number; mean: number; n: number }[] }) {
  const top = Math.ceil(Math.max(1, ...levels.map((l) => l.max)));
  const ticks = Array.from({ length: top + 1 }, (_, i) => i);
  return (
    <div>
      <div className="space-y-2.5">
        {levels.map((l) => (
          <div key={l.delay} className="grid grid-cols-[4.5rem_1fr_4.5rem] items-center gap-3 text-xs"
            title={`${l.delay} ms delay · max |error| ${l.max} ms · mean ${l.mean} ms · n=${l.n}`}>
            <span className="text-right text-muted num">{l.delay} ms</span>
            <div className="relative h-5">
              {ticks.map((t) => <div key={t} className="absolute inset-y-0 w-px bg-line" style={{ left: `${(t / top) * 100}%` }} aria-hidden />)}
              <div className="absolute inset-y-1 left-0 rounded-r bg-info" style={{ width: `${(l.max / top) * 100}%` }} />
            </div>
            <span className="font-semibold num">{fmt(l.max, "ms", 3)}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-[4.5rem_1fr_4.5rem] gap-3 text-[10px] text-muted num">
        <span />
        <div className="relative h-3">{ticks.map((t) => <span key={t} className="absolute -translate-x-1/2" style={{ left: `${(t / top) * 100}%` }}>{t}</span>)}</div>
        <span>ms</span>
      </div>
      <p className="mt-3 text-xs text-muted">Bars: the largest absolute error over 20 repetitions at each programmed agent delay.</p>
    </div>
  );
}

const REPO = (import.meta.env.VITE_REPO_URL as string | undefined) ?? "https://github.com/hamzaahmad3006/gauntlet";

export default function Calibration() {
  const q = useCalibration();
  if (q.isLoading) return <Skeleton rows={6} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const c = q.data!;
  if (c.bound_ms == null) return <EmptyState title="No calibration artefact committed">No measurement error bound is claimed until one is.</EmptyState>;
  const levels = Object.entries(c.per_level ?? {});
  return (
    <>
      <PageHeader eyebrow="Trust" title="Calibration — the rig's own error" subtitle="A measurement product that cannot state its accuracy has produced opinions. This is GAUNTLET's." actions={<EvidenceLabel kind="MEASURED" />} />
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Error bound (max |error|)" value={`${c.bound_ms} ms`} status={c.passed ?? null} threshold={`${c.acceptable_max_ms} ms acceptable max`} />
        <Stat label="Repetitions" value={c.n} sub={`${c.delays_ms?.length} delays × ${c.repetitions}`} />
        <Stat label="Commit" value={<span className="mono text-base">{c.git_sha?.slice(0, 10)}</span>} sub={c.run_at} />
        <Stat label="Environment" value={<span className="text-sm">{c.environment}</span>} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="How much of the allowed error is used" actions={<EvidenceLabel kind="MEASURED" />}>
          <ErrorBudget bound={c.bound_ms} max={c.acceptable_max_ms ?? 50} />
        </Panel>
        <Panel title="Worst error at each programmed delay" actions={<EvidenceLabel kind="MEASURED" />}>
          <DelayBars levels={levels.map(([k, v]) => ({ delay: k, max: v.max_abs_error_ms, mean: v.mean_error_ms, n: v.n }))} />
        </Panel>
        <Panel title="Per programmed delay" pad={false}>
          <DataTable rows={levels} rowKey={([k]) => k} columns={[
            { key: "d", header: "Delay", render: ([k]) => `${k} ms` },
            { key: "n", header: "n", align: "right", render: ([, v]) => v.n },
            { key: "m", header: "max |error|", align: "right", render: ([, v]) => fmt(v.max_abs_error_ms, "ms", 3) },
            { key: "e", header: "mean error", align: "right", render: ([, v]) => fmt(v.mean_error_ms, "ms", 3) },
            { key: "s", header: "stdev", align: "right", render: ([, v]) => fmt(v.stdev_error_ms, "ms", 3) },
            { key: "o", header: "target overshoot", align: "right", render: ([, v]) => fmt(v.mean_target_overshoot_ms, "ms", 3) },
          ]} />
        </Panel>
        <Panel title="Method and scope">
          <p className="text-sm">{c.method}.</p>
          <p className="mt-2 text-sm">The calibration target detects the end of the caller's tone at sample resolution, waits the programmed delay on the shared clock, and reports the exact instant its response left. The caller measures that response through the ordinary probe path — the same code that measures every real call. Error = probe onset − reported emit instant.</p>
          <p className="mt-2 text-sm text-warn">{c.scope_statement ?? c.scope}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone={c.passed ? "pass" : "breach"}>{c.passed ? "within acceptable max" : "exceeds acceptable max"}</Badge>
            <a className="text-sm underline" href={`${REPO}/blob/main/calibration/results.csv`} target="_blank" rel="noreferrer">raw rows (results.csv)</a>
            <a className="text-sm underline" href={`${REPO}/blob/main/calibration/run_calibration.py`} target="_blank" rel="noreferrer">runner source</a>
          </div>
        </Panel>
      </div>
    </>
  );
}
