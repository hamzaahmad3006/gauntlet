import { useEffect, useRef, useState } from "react";
import { PageHeader } from "../../../components/Layout";
import { Waveform } from "../../../components/Waveform";
import { Badge, Panel } from "../../../components/ui";
import { fmt } from "../../../components/ui/format";
import { AGENTS, useTalkToAgent, type AgentKey } from "./useTalkToAgent";

const MIC = "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm7 9a7 7 0 0 1-14 0m7 7v3";
const HANG = "M10.7 13.3a15 15 0 0 0 3.4 2.4l1.3-1.3a1.5 1.5 0 0 1 1.6-.4c.9.3 1.9.5 2.9.6a1.5 1.5 0 0 1 1.3 1.5v2.6a1.5 1.5 0 0 1-1.6 1.5A17.5 17.5 0 0 1 3.3 3.6 1.5 1.5 0 0 1 4.8 2h2.6a1.5 1.5 0 0 1 1.5 1.3c.1 1 .3 2 .6 2.9a1.5 1.5 0 0 1-.4 1.6L7.8 9.1M22 2 2 22";

function Glyph({ d, className = "h-7 w-7" }: { d: string; className?: string }) {
  return <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>;
}

/** The call orb: breathes when idle, swells with the microphone level, turns emerald while the agent talks. */
function Orb({ status, youLevel, agentSpeaking }: { status: string; youLevel: number; agentSpeaking: boolean }) {
  const live = status === "live";
  const scale = 1 + Math.min(0.28, youLevel * 5);
  const ring = agentSpeaking ? "from-emerald-400 via-teal-400 to-cyan-400" : youLevel > 0.015 ? "from-blue-500 via-indigo-500 to-violet-500" : "from-emerald-400 via-cyan-500 to-violet-500";
  const label = !live ? (status === "connecting" ? "Connecting…" : "Ready to call") : agentSpeaking ? "Agent is speaking" : youLevel > 0.015 ? "Listening to you" : "Your turn — speak";
  return (
    <div className="relative mx-auto grid h-64 w-64 place-items-center">
      {live && <span className={`ping-soft absolute h-44 w-44 rounded-full bg-gradient-to-br ${ring} opacity-40`} />}
      <div className={`spin-slow absolute h-60 w-60 rounded-full bg-gradient-to-br ${ring} opacity-25 blur-2xl`} />
      <div className={`absolute h-52 w-52 rounded-full border-2 border-dashed ${live ? "spin-slow border-cyan-300/70" : "border-slate-200"}`} />
      <div className={`relative grid h-40 w-40 place-items-center rounded-full bg-gradient-to-br ${ring} shadow-2xl shadow-cyan-500/30 transition-transform duration-100 ${live ? "" : "orb-idle"}`}
        style={{ transform: `scale(${live ? scale : 1})` }}>
        <div className="grid h-[88%] w-[88%] place-items-center rounded-full bg-white/15 backdrop-blur">
          {live ? <Waveform bars={14} className="h-14" tone="white" active={agentSpeaking || youLevel > 0.015} /> : <Glyph d={MIC} className="h-12 w-12 text-white" />}
        </div>
      </div>
      <div className="absolute -bottom-2 rounded-full border border-line bg-white px-3 py-1 text-xs font-semibold shadow-sm">{label}</div>
    </div>
  );
}

export default function TalkToAgent() {
  const T = useTalkToAgent();
  const [agent, setAgent] = useState<AgentKey>("tuned");
  const live = T.status === "live" || T.status === "connecting";
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { const box = end.current?.parentElement; if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" }); }, [T.lines.length]);
  const latencies = T.lines.map((l) => l.latencyMs).filter((v): v is number => v != null);
  const avg = latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : null;

  return (
    <>
      <PageHeader eyebrow="Live voice demo" title="Talk to the agent yourself"
        subtitle="Call the bundled restaurant agent from your browser. Speak English into your microphone and it answers out loud — try booking a table." />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="space-y-5">
          <section className="glass relative overflow-clip rounded-3xl p-6">
            <div className="bg-gradient-brand blob pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full opacity-15 blur-3xl" aria-hidden />
            <div className="relative grid grid-cols-2 gap-2">
              {(Object.keys(AGENTS) as AgentKey[]).map((k) => (
                <button key={k} disabled={live} onClick={() => setAgent(k)}
                  className={`rounded-2xl border p-3 text-left transition disabled:cursor-not-allowed ${agent === k ? "ring-accent border-transparent bg-white" : "border-line bg-white/60 hover:bg-white"} ${live && agent !== k ? "opacity-40" : ""}`}>
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <span className={`h-2 w-2 rounded-full ${k === "tuned" ? "bg-emerald-500" : "bg-amber-500"}`} />
                    {k === "tuned" ? "Tuned agent" : "Slow agent"}
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted">{k === "tuned" ? "answers after a 450 ms pause, stops when interrupted" : "waits 900 ms, never stops when interrupted"}</div>
                </button>
              ))}
            </div>
            <div className="relative mt-6"><Orb status={T.status} youLevel={T.youLevel} agentSpeaking={T.agentSpeaking} /></div>
            <div className="relative mt-8 flex flex-col items-center gap-3">
              {!live ? (
                <button onClick={() => T.start(agent)}
                  className="btn-glow grid h-16 w-16 place-items-center rounded-full transition hover:scale-105 active:scale-95" aria-label="Start call">
                  <Glyph d={MIC} />
                </button>
              ) : (
                <button onClick={T.stop}
                  className="grid h-16 w-16 place-items-center rounded-full bg-rose-500 text-white shadow-lg shadow-rose-500/40 transition hover:scale-105 active:scale-95" aria-label="End call">
                  <Glyph d={HANG} />
                </button>
              )}
              <div className="text-sm font-semibold">{live ? "End call" : "Start call"}</div>
              {T.status === "connecting" && <p className="text-xs text-muted">Allow the microphone if the browser asks.</p>}
              {T.status === "live" && <Badge tone="pass">connected · {AGENTS[agent].label}</Badge>}
              {T.status === "ended" && <Badge>call ended</Badge>}
              {T.error && <p className="text-center text-sm text-breach">{T.error}</p>}
              <label className="mt-1 flex cursor-pointer items-center gap-2 text-xs text-muted">
                <input type="checkbox" className="accent-emerald-500" checked={T.headphones} onChange={(e) => T.setHeadphones(e.target.checked)} />
                I&apos;m wearing headphones (lets you interrupt the agent)
              </label>
            </div>
          </section>
          <div className="grid grid-cols-2 gap-3">
            <div className="glass rounded-2xl p-4">
              <div className="text-[11px] uppercase tracking-[0.12em] text-muted">Replies</div>
              <div className="mt-1 text-2xl font-bold num">{T.lines.filter((l) => l.speaker === "agent").length}</div>
            </div>
            <div className="glass rounded-2xl p-4">
              <div className="text-[11px] uppercase tracking-[0.12em] text-muted">Avg. answer time</div>
              <div className={`mt-1 text-2xl font-bold num ${avg == null ? "" : avg > 1500 ? "text-breach" : "text-pass"}`}>{fmt(avg, "ms", 0)}</div>
            </div>
          </div>
        </div>

        <Panel title="Conversation" actions={<span className="text-[11px] text-muted">answer time measured in your browser</span>}>
          <div className="h-[34rem] space-y-3 overflow-y-auto pr-1">
            {T.lines.length === 0 && (
              <div className="grid h-full place-items-center">
                <div className="max-w-sm text-center">
                  <Waveform bars={28} className="mx-auto h-16" active={live} tone={live ? "brand" : "muted"} />
                  <div className="mt-5 font-semibold">{live ? "Listen for the greeting…" : "Your conversation appears here"}</div>
                  <p className="mt-1 text-sm text-muted">
                    {live ? "Then say something like: “Hi, I'd like a table for two on Saturday at 8pm, under the name Hamza.”"
                      : "Pick an agent and press the microphone. What the agent hears, what it says and how long it took appear live."}
                  </p>
                </div>
              </div>
            )}
            {T.lines.map((l, i) => (
              <div key={i} className={`float-in flex gap-2.5 ${l.speaker === "you" ? "flex-row-reverse" : ""}`}>
                <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-bold text-white shadow ${l.speaker === "you" ? "bg-gradient-to-br from-blue-500 to-indigo-500" : "bg-gradient-to-br from-emerald-400 to-teal-500"}`}>
                  {l.speaker === "you" ? "You" : "AI"}
                </div>
                <div className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm shadow-sm ${l.speaker === "you" ? "rounded-tr-md bg-gradient-to-br from-blue-500 to-indigo-500 text-white" : "rounded-tl-md border border-line bg-white"}`}>
                  <div className={`mb-1 flex items-center justify-between gap-4 text-[10px] font-semibold uppercase tracking-wider ${l.speaker === "you" ? "text-white/70" : "text-emerald-600"}`}>
                    <span>{l.speaker === "you" ? "You · as the agent heard you" : "Bella Tavola agent"}</span>
                    {l.speaker === "agent" && l.latencyMs != null && (
                      <span className={`rounded-full px-2 py-0.5 normal-case tracking-normal num ${l.latencyMs > 1500 ? "bg-rose-50 text-rose-600" : "bg-emerald-50 text-emerald-700"}`}>
                        ⏱ {fmt(l.latencyMs, "ms", 0)}
                      </span>
                    )}
                  </div>
                  <div className="leading-relaxed">{l.text}</div>
                  {l.speaker === "agent" && l.timings && l.timings.llm_ms != null && (
                    <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-panel2" title="time inside the agent">
                      {[["stt_ms", "bg-sky-400"], ["llm_ms", "bg-violet-400"], ["tts_ms", "bg-emerald-400"]].map(([k, c]) => (
                        <div key={k} className={c} style={{ width: `${(100 * (l.timings![k] ?? 0)) / ((l.timings!.stt_ms ?? 0) + (l.timings!.llm_ms ?? 0) + (l.timings!.tts_ms ?? 0) || 1)}%` }} />
                      ))}
                    </div>
                  )}
                  {l.speaker === "agent" && l.timings && l.timings.llm_ms != null && (
                    <div className="mt-1 flex gap-3 text-[10px] text-muted num">
                      <span><span className="text-sky-500">●</span> hearing {fmt(l.timings.stt_ms, "ms", 0)}</span>
                      <span><span className="text-violet-500">●</span> thinking {fmt(l.timings.llm_ms, "ms", 0)}</span>
                      <span><span className="text-emerald-500">●</span> voice {fmt(l.timings.tts_ms, "ms", 0)}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={end} />
          </div>
          <p className="mt-3 border-t border-line pt-3 text-xs text-muted">
            <b className="text-fg">Answer time</b> runs from your last spoken word to the agent&apos;s first sound reaching your browser,
            so it includes the network both ways. Above about 1,500 ms a phone conversation starts to feel slow.
          </p>
        </Panel>
      </div>
    </>
  );
}
