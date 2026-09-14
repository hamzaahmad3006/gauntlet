import { Link } from "react-router-dom";
import { ApiError } from "../../../api/client";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, ErrorState, Field, Input, Panel, Select, Skeleton } from "../../../components/ui";
import { dur, fmt, humanize } from "../../../components/ui/format";
import { useNewRun } from "./useNewRun";

export default function NewRun() {
  const { targets, suites, conditions, thresholds, suite, form, set, toggle, estimate, start, quick } = useNewRun();
  if (targets.isLoading || suites.isLoading) return <Skeleton rows={6} />;
  const cond = conditions.data?.find((c) => c.key === form.condition_profile_key);
  const startErr = start.error instanceof ApiError ? start.error : null;
  const nScen = form.scenario_keys.length || suite?.scenarios.length || 0;
  const nPers = form.persona_keys.length || suite?.personas.length || 0;
  return (
    <>
      <PageHeader title="New benchmark run" subtitle="Every knob shows its exact value. The estimate recomputes before anything is spent." />
      <section className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-pass/40 bg-pass/5 px-4 py-3">
        <div className="max-w-2xl text-sm">
          <div className="font-semibold">First time? Watch one call.</div>
          <div className="text-muted">
            GAUNTLET's AI caller phones the bundled restaurant agent and tries to book a table. You watch the
            conversation live, then hear the recording and see how fast the agent answered. One call, about 1½ minutes.
          </div>
        </div>
        <Button variant="primary" className="px-5 py-2.5" busy={quick.isPending} onClick={() => quick.mutate()} disabled={!targets.data?.length || !suites.data?.length}>
          ▶ Start a 1-call demo
        </Button>
        {quick.error && <div className="w-full text-sm text-breach">{(quick.error as Error).message}</div>}
      </section>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Panel title="What is tested">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Target">
                <Select value={form.target_id} onChange={(e) => set("target_id", e.target.value)}>
                  {targets.data?.map((t) => <option key={t.id} value={t.id} disabled={!t.verified_at}>{t.name}{t.verified_at ? "" : " (unverified)"}</option>)}
                </Select>
              </Field>
              <Field label="Suite" hint={suite && <span className="mono">hash {suite.version_hash.slice(0, 12)}…</span>}>
                <Select value={form.suite_id} onChange={(e) => set("suite_id", e.target.value)}>
                  {suites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </Select>
              </Field>
            </div>
            {suite && (
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <div className="mb-1 text-xs uppercase tracking-wider text-muted">Scenarios {form.scenario_keys.length ? `(${form.scenario_keys.length} selected)` : "(all)"}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {suite.scenarios.map((s) => (
                      <button key={s.key} type="button" onClick={() => toggle("scenario_keys", s.key)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition ${form.scenario_keys.includes(s.key) ? "border-transparent bg-info text-white shadow-sm" : "border-line bg-white text-muted hover:border-info/50 hover:text-fg"}`}>
                        {humanize(s.key)}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-xs uppercase tracking-wider text-muted">Personas {form.persona_keys.length ? `(${form.persona_keys.length} selected)` : "(all)"}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {suite.personas.map((p) => (
                      <button key={p.key} type="button" onClick={() => toggle("persona_keys", p.key)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition ${form.persona_keys.includes(p.key) ? "border-transparent bg-info text-white shadow-sm" : "border-line bg-white text-muted hover:border-info/50 hover:text-fg"}`}>
                        {humanize(p.key)}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Panel>
          <Panel title="Under what conditions">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Condition profile">
                <Select value={form.condition_profile_key} onChange={(e) => set("condition_profile_key", e.target.value)}>
                  {conditions.data?.map((c) => <option key={c.key} value={c.key}>{humanize(c.key)}</option>)}
                </Select>
              </Field>
              <Field label="Threshold profile">
                <Select value={form.threshold_profile_key} onChange={(e) => set("threshold_profile_key", e.target.value)}>
                  {thresholds.data?.map((t) => <option key={t.key + t.version_hash} value={t.key}>{t.key} ({t.version_hash.slice(0, 8)})</option>)}
                </Select>
              </Field>
            </div>
            <div className="mt-3 rounded-md border border-line bg-bg p-3 text-xs mono">
              {cond && Object.keys(cond.parameters).length ? Object.entries(cond.parameters).map(([k, v]) => (
                <div key={k}><span className="text-muted">{k}</span> {JSON.stringify(v)}</div>
              )) : <span className="text-muted">clean — no impairment (CH-01 baseline)</span>}
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <Field label="Concurrency"><Input type="number" min={1} max={20} value={form.concurrency} onChange={(e) => set("concurrency", Number(e.target.value))} /></Field>
              <Field label="Repeats"><Input type="number" min={1} max={5} value={form.repeats} onChange={(e) => set("repeats", Number(e.target.value))} /></Field>
              <Field label="Spend cap (USD)"><Input inputMode="decimal" placeholder="default" value={form.spend_cap_usd} onChange={(e) => set("spend_cap_usd", e.target.value)} /></Field>
              <Field label="Seed" hint="empty = new"><Input inputMode="numeric" value={form.seed} onChange={(e) => set("seed", e.target.value)} /></Field>
            </div>
            <div className="mt-3"><Field label="Label (shown in comparisons)"><Input value={form.label} onChange={(e) => set("label", e.target.value)} placeholder="e.g. endpointing 450 ms" /></Field></div>
          </Panel>
        </div>
        <div className="space-y-4">
          <Panel title="Estimate — before anything is spent">
            {estimate.isError ? <ErrorState error={estimate.error} /> : (
              <div className={`space-y-3 ${estimate.isFetching ? "opacity-60" : ""}`}>
                <div className="grid grid-cols-3 gap-2 text-center num">
                  <div><div className="text-2xl font-semibold">{estimate.data?.calls ?? nScen * nPers * form.repeats}</div><div className="text-xs text-muted">calls</div></div>
                  <div><div className="text-2xl font-semibold">{dur((estimate.data?.estimated_duration_s ?? 0) * 1000)}</div><div className="text-xs text-muted">wall clock</div></div>
                  <div><div className="text-2xl font-semibold">{fmt(estimate.data?.estimated_rig_cost_usd ?? 0, "USD")}</div><div className="text-xs text-muted">rig cost</div></div>
                </div>
                <ul className="list-disc space-y-1 pl-4 text-xs text-muted">{estimate.data?.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
                {(estimate.data?.calls ?? 0) < 20 && <Badge tone="warn">Fewer than 20 calls: no grade will be emitted</Badge>}
              </div>
            )}
          </Panel>
          <Button variant="primary" className="w-full py-2.5" busy={start.isPending} onClick={() => start.mutate()} disabled={!form.target_id || !form.suite_id}>
            Start run
          </Button>
          {startErr && (
            <div className="text-sm text-breach">
              {startErr.message}
              {startErr.code === "target_not_verified" && <> — <Link className="underline" to={`/dashboard/targets/${form.target_id}`}>verify it</Link></>}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
