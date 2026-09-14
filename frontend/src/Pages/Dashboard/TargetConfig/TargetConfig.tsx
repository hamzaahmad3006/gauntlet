import { Link } from "react-router-dom";
import type { DiagStatus, Diagnostic } from "../../../api/types";
import { PageHeader } from "../../../components/Layout";
import { Badge, Button, ErrorState, Field, Input, Panel, Select, Skeleton } from "../../../components/ui";
import { ago } from "../../../components/ui/format";
import { useTargetConfig } from "./useTargetConfig";

const DIAG_ROWS: [keyof Diagnostic, string][] = [
  ["connection", "Connection"], ["audio_out", "Audio out (caller → agent)"], ["audio_in", "Audio in (agent → caller)"], ["transcript", "Referee transcript"],
];

function DiagRow({ label, s, pending }: { label: string; s?: DiagStatus; pending: boolean }) {
  const tone = pending ? "live" : s?.status === "ok" ? "pass" : s?.status === "failed" ? "breach" : "muted";
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line/60 py-2 last:border-0">
      <div>
        <div className="text-sm">{label}</div>
        {s?.hint && <div className="text-xs text-muted">{s.hint}</div>}
        {s?.reason && <div className="text-xs text-breach mono">{s.reason}</div>}
      </div>
      <Badge tone={tone}>{pending ? "checking…" : s?.status?.replace("_", " ") ?? "not run"}</Badge>
    </div>
  );
}

const WS_SNIPPET = `# minimal gauntlet.pcm.v1 server (Python, websockets)
async def handler(ws):
    hello = json.loads(await ws.recv())            # {"type":"hello","nonce":...}
    await ws.send(json.dumps({"type": "hello", "protocol": "gauntlet.pcm.v1", "nonce": hello["nonce"]}))
    async for msg in ws:                           # 640-byte frames: 20 ms, 16 kHz mono s16le
        if isinstance(msg, bytes):
            reply = my_agent.process(msg)          # your pipeline; send back 640-byte frames, paced 20 ms
            if reply: await ws.send(reply)`;

export default function TargetConfig() {
  const { isNew, target, form, set, save, verify, diagnose, fieldError } = useTargetConfig();
  const t = target.data;
  if (!isNew && target.isLoading) return <Skeleton rows={6} />;
  if (!isNew && target.isError) return <ErrorState error={target.error} retry={() => target.refetch()} />;
  const diag = diagnose.data ?? t?.last_diagnostic ?? undefined;
  const adapter = t?.adapter ?? form.adapter;
  return (
    <>
      <PageHeader eyebrow={isNew ? "New target" : "Target"} title={isNew ? "Connect your voice agent" : t?.name}
        subtitle={isNew ? "Register the agent, prove you own it, then run one diagnostic call." : t?.description ?? t?.connection_hint}
        actions={t && <Link to={`/dashboard/runs/new?target=${t.id}`}><Button variant="primary" disabled={!t.verified_at}>Run suite</Button></Link>} />
      <div className="grid gap-4 lg:grid-cols-5">
        <Panel title={isNew ? "Connection" : "Update connection"} className="lg:col-span-3">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name" error={fieldError?.field === "/name" ? fieldError.message : null}>
                <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder={t?.name ?? "My booking agent"} required={isNew} />
              </Field>
              <Field label="Adapter" hint={isNew ? "Immutable after creation." : "Adapter type cannot change."}>
                <Select value={adapter} disabled={!isNew} onChange={(e) => set("adapter", e.target.value as "websocket_pcm" | "livekit")}>
                  <option value="websocket_pcm">WebSocket PCM (gauntlet.pcm.v1)</option>
                  <option value="livekit">LiveKit room (WebRTC)</option>
                </Select>
              </Field>
            </div>
            <Field label={adapter === "livekit" ? "LiveKit URL" : "Endpoint URL"} error={fieldError?.field?.startsWith("/connection") ? fieldError.message : null}
              hint={isNew ? "wss:// only. Private, loopback and cloud-metadata addresses are rejected." : "Leave empty to keep the current connection. Changing it revokes verification."}>
              <Input value={form.url} onChange={(e) => set("url", e.target.value)} placeholder={adapter === "livekit" ? "wss://your-project.livekit.cloud" : "wss://agent.example.com/gauntlet"} />
            </Field>
            {adapter === "websocket_pcm" ? (
              <Field label="Bearer token (optional)" hint="Write-only: after saving only a masked hint is ever shown.">
                <Input type="password" value={form.token} onChange={(e) => set("token", e.target.value)} autoComplete="off" />
              </Field>
            ) : (
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="API key"><Input value={form.apiKey} onChange={(e) => set("apiKey", e.target.value)} autoComplete="off" /></Field>
                <Field label="API secret"><Input type="password" value={form.apiSecret} onChange={(e) => set("apiSecret", e.target.value)} autoComplete="off" /></Field>
                <Field label="Room" hint="{call_id} is replaced per call"><Input value={form.room} onChange={(e) => set("room", e.target.value)} /></Field>
              </div>
            )}
            <details className="rounded-md border border-line p-3">
              <summary className="cursor-pointer text-sm">Declare pipeline unit prices (enables the estimated target-cost model)</summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-4">
                <Field label="LLM prompt $/1k tok"><Input inputMode="decimal" value={form.llmPrompt} onChange={(e) => set("llmPrompt", e.target.value)} /></Field>
                <Field label="LLM completion $/1k tok"><Input inputMode="decimal" value={form.llmCompletion} onChange={(e) => set("llmCompletion", e.target.value)} /></Field>
                <Field label="TTS $/1k chars"><Input inputMode="decimal" value={form.ttsChars} onChange={(e) => set("ttsChars", e.target.value)} /></Field>
                <Field label="STT $/min"><Input inputMode="decimal" value={form.sttMinute} onChange={(e) => set("sttMinute", e.target.value)} /></Field>
              </div>
              <p className="mt-2 text-xs text-muted">Undeclared components are listed by name in reports. Target cost is always labelled estimated.</p>
            </details>
            {fieldError && !fieldError.field && <p className="text-sm text-breach">{fieldError.message}</p>}
            <Button type="submit" variant="primary" busy={save.isPending}>{isNew ? "Save target" : "Save changes"}</Button>
          </form>
          {isNew && adapter === "websocket_pcm" && (
            <div className="mt-5">
              <div className="mb-1 text-xs uppercase tracking-wider text-muted">About thirty lines of server code is enough</div>
              <pre className="overflow-x-auto rounded-md border border-line bg-bg p-3 text-xs mono">{WS_SNIPPET}</pre>
            </div>
          )}
        </Panel>
        {isNew && (
          <div className="space-y-4 lg:col-span-2">
            <Panel title="Three steps to your first run">
              <ol className="space-y-4">
                {[
                  ["Register the endpoint", "Name the agent and give GAUNTLET its WebSocket URL, or a LiveKit room. Nothing is installed inside the agent."],
                  ["Prove you own it", "GAUNTLET sends a one-time nonce in its hello; your server echoes it back. Only verified targets can be load-tested."],
                  ["Run one diagnostic call", "Connection, audio out, audio in and transcript are each checked and explained before any benchmark spends money."],
                ].map(([title, text], i) => (
                  <li key={title} className="flex gap-3">
                    <span className="bg-gradient-brand grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold text-white shadow">{i + 1}</span>
                    <div><div className="font-semibold">{title}</div><p className="mt-0.5 text-sm text-muted">{text}</p></div>
                  </li>
                ))}
              </ol>
            </Panel>
            <Panel title="Just exploring?">
              <p className="text-sm text-muted">Two bundled synthetic agents are already verified in your workspace, so you can try everything first.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <a href="/dashboard/talk" className="btn-glow rounded-lg px-3 py-1.5 text-sm font-semibold no-underline">Talk to the agent</a>
                <a href="/dashboard/runs/new" className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-semibold no-underline shadow-sm">Run a 1-call demo</a>
              </div>
            </Panel>
          </div>
        )}
        {!isNew && t && (
          <div className="space-y-4 lg:col-span-2">
            <Panel title="Ownership verification">
              {t.verified_at ? (
                <div className="flex items-center gap-2 text-sm"><Badge tone="pass">verified</Badge><span className="text-muted">{ago(t.verified_at)}</span></div>
              ) : (
                <div className="space-y-2 text-sm">
                  <p className="text-muted">Unverified targets cannot be dialled. WebSocket targets must echo a fresh nonce in their hello frame; LiveKit targets verify by joining with your credentials.</p>
                  <Button variant="primary" busy={verify.isPending} onClick={() => verify.mutate()}>Verify now</Button>
                  {verify.data?.failure_reason && <p className="text-xs text-breach">{verify.data.failure_reason}</p>}
                </div>
              )}
            </Panel>
            <Panel title="Diagnostic call" actions={<Button busy={diagnose.isPending} disabled={!t.verified_at} onClick={() => diagnose.mutate()}>Run diagnostic</Button>}>
              {DIAG_ROWS.map(([k, label]) => <DiagRow key={k} label={label} s={diag?.[k] as DiagStatus | undefined} pending={diagnose.isPending} />)}
              {diagnose.isError && <ErrorState error={diagnose.error} />}
              {diag?.checked_at && <div className="mt-2 text-xs text-muted">last checked {ago(diag.checked_at)}</div>}
            </Panel>
          </div>
        )}
      </div>
    </>
  );
}
