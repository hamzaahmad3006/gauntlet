import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { PageHeader } from "../../../components/Layout";
import { Badge, DataTable, EmptyState, ErrorState, Panel, Skeleton, Stat } from "../../../components/ui";
import { fmt } from "../../../components/ui/format";
import { useCalibration } from "./useCalibration";

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
      <PageHeader title="Calibration — the rig's own error" subtitle="A measurement product that cannot state its accuracy has produced opinions. This is GAUNTLET's." actions={<EvidenceLabel kind="MEASURED" />} />
      <div className="grid gap-4 sm:grid-cols-4">
        <Panel><Stat label="Error bound (max |error|)" value={`${c.bound_ms} ms`} status={c.passed ?? null} threshold={`${c.acceptable_max_ms} ms acceptable max`} /></Panel>
        <Panel><Stat label="Repetitions" value={c.n} sub={`${c.delays_ms?.length} delays × ${c.repetitions}`} /></Panel>
        <Panel><Stat label="Commit" value={<span className="mono text-base">{c.git_sha?.slice(0, 10)}</span>} sub={c.run_at} /></Panel>
        <Panel><Stat label="Environment" value={<span className="text-sm">{c.environment}</span>} /></Panel>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
