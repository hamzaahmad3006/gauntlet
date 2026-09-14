import { useEffect, useRef, useState } from "react";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, Panel } from "../../../components/ui";
import { fmt } from "../../../components/ui/format";
import { AGENTS, useTalkToAgent, type AgentKey } from "./useTalkToAgent";

function Meter({ label, level, active, tone }: { label: string; level: number; active: boolean; tone: "info" | "pass" }) {
  const width = Math.min(100, Math.round(level * 600));
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs">
        <span className={`h-2.5 w-2.5 rounded-full ${active ? (tone === "info" ? "pulse bg-info" : "pulse bg-pass") : "bg-line"}`} />
        <span className={active ? "font-semibold" : "text-muted"}>{label}{active ? " — speaking" : ""}</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-panel2">
        <div className={`h-full transition-[width] duration-75 ${tone === "info" ? "bg-info" : "bg-pass"}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export default function TalkToAgent() {
  const T = useTalkToAgent();
  const [agent, setAgent] = useState<AgentKey>("tuned");
  const live = T.status === "live" || T.status === "connecting";
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [T.lines.length]);

  return (
    <>
      <PageHeader title="Talk to the agent yourself"
        subtitle="Call the bundled restaurant agent from your browser. Speak into your microphone and it answers out loud. Try booking a table." />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <Panel title="Call">
            <div className="space-y-3">
              <div>
                <div className="mb-1 text-xs uppercase tracking-wider text-muted">Agent</div>
                <div className="grid gap-2">
                  {(Object.keys(AGENTS) as AgentKey[]).map((k) => (
                    <button key={k} disabled={live} onClick={() => setAgent(k)}
                      className={`rounded-md border px-3 py-2 text-left text-sm disabled:opacity-60 ${agent === k ? "border-info bg-info/10" : "border-line"}`}>
                      {AGENTS[k].label}
                    </button>
                  ))}
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={T.headphones} onChange={(e) => T.setHeadphones(e.target.checked)} />
                I&apos;m wearing headphones
              </label>
              <p className="text-[11px] text-muted">
                Without headphones your microphone is muted while the agent talks, so it does not hear itself.
                With headphones you can interrupt it mid-sentence.
              </p>
              {!live
                ? <Button variant="primary" className="w-full py-3 text-base" onClick={() => T.start(agent)}>🎙 Start call</Button>
                : <Button variant="danger" className="w-full py-3 text-base" onClick={T.stop}>End call</Button>}
              {T.status === "connecting" && <p className="text-sm text-muted">Connecting… allow the microphone if the browser asks.</p>}
              {T.status === "live" && <Badge tone="pass">connected — the agent greets you first</Badge>}
              {T.error && <p className="text-sm text-breach">{T.error}</p>}
            </div>
          </Panel>
          <Panel title="Who is speaking">
            <div className="space-y-3">
              <Meter label="You" level={T.youLevel} active={T.youLevel > 0.015} tone="info" />
              <Meter label="Agent" level={T.agentSpeaking ? 0.12 : 0} active={T.agentSpeaking} tone="pass" />
            </div>
          </Panel>
          <Panel title="What the numbers mean">
            <p className="text-xs text-muted">
              <b className="text-fg">Answered after</b> is the time from your last spoken word to the agent&apos;s first sound
              reaching your browser. It is measured here in the browser, so it includes the network both ways. A phone
              conversation starts to feel slow above about 1,500 ms. The agent first waits for a pause (450 ms for the
              tuned agent, 900 ms for the slow one), then transcribes you, thinks and speaks.
            </p>
          </Panel>
        </div>
        <div className="lg:col-span-2">
          <Panel title="Conversation">
            <div className="max-h-[32rem] min-h-80 space-y-2 overflow-y-auto pr-1">
              {T.lines.length === 0 && (
                <div className="rounded-md border border-dashed border-line p-6 text-center text-sm text-muted">
                  {live
                    ? "Listen for the greeting, then say something like: Hi, I'd like a table for two on Saturday at 8pm."
                    : "Press Start call. What you say and what the agent answers will appear here."}
                </div>
              )}
              {T.lines.map((l, i) => (
                <div key={i} className={`flex ${l.speaker === "you" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-lg border px-3 py-2 text-sm ${l.speaker === "you" ? "border-info/40 bg-info/10" : "border-pass/40 bg-pass/10"}`}>
                    <div className="mb-0.5 flex items-center justify-between gap-3 text-[11px] text-muted">
                      <span className="font-semibold">{l.speaker === "you" ? "You (as the agent heard you)" : "Agent"}</span>
                      {l.speaker === "agent" && l.latencyMs != null && (
                        <span className={`num ${l.latencyMs > 1500 ? "text-breach" : "text-pass"}`}>answered after {fmt(l.latencyMs, "ms", 0)}</span>
                      )}
                    </div>
                    {l.text}
                    {l.speaker === "agent" && l.timings && l.timings.llm_ms != null && (
                      <div className="mt-1 text-[11px] text-muted num">
                        inside the agent: hearing {fmt(l.timings.stt_ms, "ms", 0)} · thinking {fmt(l.timings.llm_ms, "ms", 0)} · voice {fmt(l.timings.tts_ms, "ms", 0)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={end} />
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
