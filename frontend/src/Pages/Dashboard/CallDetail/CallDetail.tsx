import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, DataTable, ErrorState, Panel, Skeleton, Stat } from "../../../components/ui";
import { dur, fmt, short } from "../../../components/ui/format";
import { useCallDetail } from "./useCallDetail";
import { WaveformPair } from "./WaveformPair";

export default function CallDetail() {
  const { detail, waveform, audioUrl, audioError, loadAudio } = useCallDetail();
  const [cursor, setCursor] = useState<number | undefined>();
  if (detail.isLoading) return <Skeleton rows={8} />;
  if (detail.isError) return <ErrorState error={detail.error} retry={() => detail.refetch()} />;
  const d = detail.data!;
  const c = d.call;
  const imp = (c.achieved_impairment ?? {}) as Record<string, unknown>;
  const applied = (c.interruptions ?? []).filter((i) => i.status === "applied");
  const transcriptTurns = d.turns.filter((t) => t.caller_text || t.agent_text || t.t_agent_first_audio_ms != null);
  return (
    <>
      <PageHeader title={<span className="mono">{c.scenario_key}</span>}
        subtitle={<>{c.persona_key} · call {short(c.id)} · seed <span className="mono">{c.seed}</span> · <Link to={`/dashboard/runs/${c.run_id}`} className="underline">run {short(c.run_id)}</Link></>}
        actions={<Badge tone={c.status === "completed" ? "pass" : c.status === "errored" ? "breach" : "warn"}>{c.status}{c.reason_code ? ` · ${c.reason_code}` : ""}</Badge>} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        <Stat label="Duration" value={dur(c.duration_ms)} />
        <Stat label="Talk-over" value={fmt(c.talkover_ms, "ms", 0)} />
        <Stat label="Dead air" value={fmt(c.dead_air_ratio, "%")} />
        <Stat label="Barge-in stops" value={applied.length ? applied.map((i) => (i.no_yield ? "no-yield" : Math.round(i.barge_stop_ms ?? 0))).join(" · ") : "—"} sub={applied.length ? "ms, per applied interruption" : "no interruption applied"} />
        <Stat label="Connect" value={fmt(c.connect_ms, "ms", 0)} />
        <Stat label="Cache hits" value={fmt(c.cache_hit_rate, "%")} />
      </div>
      <div className="mt-4">
        <Panel title="Paired waveforms — overlap = talk-over" actions={audioUrl ? null : <Button onClick={loadAudio}>Load audio</Button>}>
          {waveform.data ? <WaveformPair wf={waveform.data} turns={d.turns} intervals={d.intervals_ms} cursorMs={cursor} /> : <Skeleton rows={2} />}
          {audioUrl && <audio className="mt-3 w-full" controls src={audioUrl} onTimeUpdate={(e) => setCursor(e.currentTarget.currentTime * 1000)} />}
          {audioError && <p className="mt-2 text-xs text-muted">{audioError}</p>}
          <p className="mt-2 text-[11px] text-muted">Two-channel recording: channel 0 = transmitted caller audio, channel 1 = received agent audio, on one clock.</p>
        </Panel>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Turn timeline" pad={false}>
          <DataTable rows={d.turns} rowKey={(t) => String(t.idx)} rowClass={(t) => (t.censored || t.no_yield ? "text-breach" : "")} columns={[
            { key: "i", header: "#", render: (t) => t.idx },
            { key: "l", header: "Latency", align: "right", render: (t) => t.censored ? <Badge tone="breach">timeout</Badge> : fmt(t.latency_ms, "ms", 0) },
            { key: "r", header: "Raw (incl. injected)", align: "right", render: (t) => fmt(t.raw_latency_ms, "ms", 0) },
            { key: "b", header: "Barge-in", align: "right", render: (t) => t.interruption_status === "applied" ? (t.no_yield ? <Badge tone="breach">no yield</Badge> : fmt(t.barge_stop_ms, "ms", 0)) : t.interruption_status ?? "" },
            { key: "o", header: "Rig", align: "right", render: (t) => fmt(t.rig_overhead_ms, "ms", 0) },
            { key: "f", header: "", render: (t) => <span className="flex gap-1">{t.premature && <Badge tone="warn">premature</Badge>}{t.fallback_used && <Badge>fallback</Badge>}{t.epoch > 0 && <Badge tone="info">epoch {t.epoch}</Badge>}</span> },
          ]} />
        </Panel>
        <Panel title="Transcript">
          <div className="max-h-96 space-y-2 overflow-y-auto text-sm">
            {transcriptTurns.map((t) => (
              <div key={t.idx}>
                {t.caller_text && <div><span className="text-xs font-semibold text-info">caller</span> <span>{t.caller_text}</span></div>}
                {t.agent_text ? <div><span className="text-xs font-semibold text-pass">agent</span> <span>{t.agent_text}</span>{t.agent_confidence != null && <span className="ml-1 text-[11px] text-muted num">({t.agent_confidence.toFixed(2)})</span>}</div>
                  : t.t_agent_first_audio_ms != null && <div className="text-xs text-muted">agent spoke — no referee transcript</div>}
              </div>
            ))}
            {!transcriptTurns.length && <p className="text-muted">No turns recorded.</p>}
          </div>
          <p className="mt-3 text-[11px] text-muted">Referee: {c.referee_engine ?? "none"}{c.referee_error ? ` — ${c.referee_error}` : ""}. Speaker attribution is structural (separate channels), not acoustic.</p>
        </Panel>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Task verdict — every met step cites a turn">
          {!d.verdict ? <p className="text-sm text-muted">Not scored: {c.referee_engine && c.referee_engine !== "none" ? "evaluation pending or skipped" : "no referee transcript, so task success cannot be judged"}.</p> : (
            <>
              <div className="mb-2 flex gap-2">
                <Badge tone={d.verdict.needs_review ? "warn" : d.verdict.task_success ? "pass" : "breach"}>{d.verdict.needs_review ? "needs review" : d.verdict.task_success ? "success" : d.verdict.status === "scoring_failed" ? "scoring failed" : "goal not met"}</Badge>
                {d.verdict.agreement != null && <Badge>agreement {d.verdict.agreement}</Badge>}
                <Badge>{d.verdict.model} · {d.verdict.prompt_version}</Badge>
              </div>
              <ul className="space-y-1.5 text-sm">
                {d.verdict.steps.map((s) => (
                  <li key={s.step_id} className="flex gap-2">
                    <span className={s.met ? "text-pass" : "text-breach"}>{s.met ? "✓" : "✗"}</span>
                    <span>{s.text}{s.met && s.quote && <span className="block text-xs text-muted">turn {s.turn_index}: "{s.quote}"</span>}{s.demoted && <span className="block text-xs text-warn">demoted: {s.demoted}</span>}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
        <Panel title="Conditions applied to this call">
          <div className="grid grid-cols-2 gap-3 text-sm num">
            <Stat label="Frames substituted" value={`${imp.frames_substituted ?? 0} / ${imp.frames_sent ?? 0}`} sub={imp.achieved_loss_rate != null ? `achieved ${(Number(imp.achieved_loss_rate) * 100).toFixed(2)}% vs configured ${(Number(imp.configured_loss_rate ?? 0) * 100).toFixed(2)}%` : undefined} />
            <Stat label="Injected delay" value={fmt(imp.injected_delay_ms as number, "ms", 0)} />
            <Stat label="Jitter achieved" value={imp.achieved_jitter_mean_ms != null ? `${fmt(imp.achieved_jitter_mean_ms as number, "ms")} ± ${fmt(imp.achieved_jitter_stddev_ms as number)}` : "—"} />
            <Stat label="SNR achieved" value={imp.achieved_snr_db != null ? `${fmt(imp.achieved_snr_db as number, "dB")}` : "—"} sub={imp.configured_snr_db != null ? `configured ${imp.configured_snr_db} dB` : undefined} />
          </div>
          {Boolean(imp.impairment_deviation) && <p className="mt-2 text-xs text-warn">Achieved loss deviates more than 1 point from configured (flagged).</p>}
          <details className="mt-3 text-xs"><summary className="cursor-pointer text-muted">Event log ({d.events.length})</summary>
            <div className="mt-2 max-h-64 overflow-y-auto mono">{d.events.map((e, i) => <div key={i}><span className="text-muted">{(e.t_ms / 1000).toFixed(3)}s</span> {e.kind} {Object.keys(e.payload).length ? JSON.stringify(e.payload) : ""}</div>)}</div>
          </details>
        </Panel>
      </div>
    </>
  );
}
