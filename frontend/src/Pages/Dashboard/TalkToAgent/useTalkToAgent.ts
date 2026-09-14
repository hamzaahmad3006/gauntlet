import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "../../../api/client";

// The two bundled agent configurations (mirrors backend/gauntlet/db/seed.py BUNDLED_TARGETS).
export const AGENTS = {
  tuned: { label: "Tuned agent (fast)", query: "mode=reference&model=qwen/qwen3.6-27b&endpoint_ms=450&delay_ms=250&yield_ms=220&greeting=1" },
  slow: { label: "Slow agent (badly tuned)", query: "mode=reference&model=openai/gpt-oss-120b&endpoint_ms=900&delay_ms=650&yield_ms=never&greeting=1" },
} as const;
export type AgentKey = keyof typeof AGENTS;

export interface TalkLine { speaker: "you" | "agent"; text: string | null; latencyMs: number | null; timings?: Record<string, number> }
type Status = "idle" | "connecting" | "live" | "ended" | "error";

const RATE = 16000;
const FRAME = 320; // 20 ms at 16 kHz, gauntlet.pcm.v1
const VOICE_RMS = 0.015; // about -36 dBFS
const AGENT_RMS = 0.01;

function wsUrl(query: string): string {
  const base = API_BASE || window.location.origin;
  return `${base.replace(/^http/, "ws")}/fixtures/agent?${query}`;
}

const rms = (x: Float32Array) => Math.sqrt(x.reduce((a, v) => a + v * v, 0) / x.length);

/** A browser softphone for the bundled agent: microphone frames out, agent frames back, over the same
 * WebSocket PCM protocol the rig uses. The response time is measured in the browser from the last voiced
 * microphone frame to the first voiced agent frame received, so it includes the network both ways. */
export function useTalkToAgent() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<TalkLine[]>([]);
  const [youLevel, setYouLevel] = useState(0);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [headphones, setHeadphones] = useState(false);
  const headphonesRef = useRef(false);
  headphonesRef.current = headphones;
  const res = useRef<{ ctx?: AudioContext; ws?: WebSocket; stream?: MediaStream; proc?: ScriptProcessorNode }>({});

  const stop = useCallback((final: Status = "ended") => {
    const r = res.current;
    try {
      if (r.ws?.readyState === WebSocket.OPEN) r.ws.send(JSON.stringify({ type: "bye", reason: "user_hung_up" }));
    } catch { /* closing anyway */ }
    r.ws?.close();
    r.proc?.disconnect();
    r.stream?.getTracks().forEach((t) => t.stop());
    void r.ctx?.close().catch(() => undefined);
    res.current = {};
    setAgentSpeaking(false);
    setYouLevel(0);
    setStatus((s) => (s === "error" || s === "idle" ? s : final));
  }, []);

  useEffect(() => () => stop(), [stop]);

  const start = useCallback(async (agent: AgentKey) => {
    setError(null);
    setLines([]);
    setStatus("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const ctx = new AudioContext({ sampleRate: RATE });
      const ws = new WebSocket(wsUrl(AGENTS[agent].query));
      ws.binaryType = "arraybuffer";
      res.current = { ctx, ws, stream };

      let playHead = 0;
      let lastYouVoiced = 0; // performance.now() of the last voiced microphone frame
      let youSpokeSinceAgent = false;
      let agentVoicedAt = 0;
      let agentActive = false;
      let pending = new Float32Array(0);

      const beginMic = () => {
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(1024, 1, 1);
        const mute = ctx.createGain();
        mute.gain.value = 0;
        src.connect(proc);
        proc.connect(mute).connect(ctx.destination);
        res.current.proc = proc;
        proc.onaudioprocess = (ev) => {
          const input = ev.inputBuffer.getChannelData(0);
          const merged = new Float32Array(pending.length + input.length);
          merged.set(pending);
          merged.set(input, pending.length);
          let i = 0;
          for (; i + FRAME <= merged.length; i += FRAME) {
            const frame = merged.subarray(i, i + FRAME);
            // without headphones the agent's own voice reaches the microphone: send silence while it talks
            const gated = !headphonesRef.current && (agentActive || performance.now() - agentVoicedAt < 400);
            const level = gated ? 0 : rms(frame);
            if (level > VOICE_RMS) { lastYouVoiced = performance.now(); youSpokeSinceAgent = true; }
            const out = new Int16Array(FRAME);
            if (!gated) for (let k = 0; k < FRAME; k++) out[k] = Math.max(-32768, Math.min(32767, frame[k] * 32767));
            if (ws.readyState === WebSocket.OPEN) ws.send(out.buffer);
            setYouLevel(level);
          }
          pending = merged.slice(i);
        };
      };

      ws.onopen = () => ws.send(JSON.stringify({
        type: "hello", protocol: "gauntlet.pcm.v1", sample_rate: RATE, frame_ms: 20, nonce: crypto.randomUUID().replace(/-/g, ""),
      }));
      ws.onerror = () => {
        setError("Could not reach the agent. Is the backend running on port 8000?");
        setStatus("error");
        stop("error");
      };
      ws.onclose = () => stop("ended");
      ws.onmessage = (ev) => {
        if (typeof ev.data === "string") {
          const msg = JSON.parse(ev.data) as { type: string; kind?: string; heard?: string | null; said?: string; timings?: Record<string, number> };
          if (msg.type === "hello") {
            setStatus("live");
            beginMic();
          } else if (msg.type === "marker" && msg.kind === "transcript") {
            const heard: TalkLine[] = msg.heard !== undefined && msg.heard !== null
              ? [{ speaker: "you", text: msg.heard || "(nothing recognised)", latencyMs: null }] : [];
            setLines((ls) => [...ls, ...heard, { speaker: "agent", text: msg.said ?? null, latencyMs: null, timings: msg.timings }]);
          }
          return;
        }
        const pcm = new Int16Array(ev.data as ArrayBuffer);
        if (pcm.length !== FRAME) return;
        let peak = 0;
        for (let k = 0; k < FRAME; k++) peak = Math.max(peak, Math.abs(pcm[k]));
        const now = performance.now();
        if (peak === 0) { // the agent's pacing silence: nothing to play
          if (agentActive && now - agentVoicedAt > 300) { agentActive = false; setAgentSpeaking(false); }
          return;
        }
        const f = new Float32Array(FRAME);
        for (let k = 0; k < FRAME; k++) f[k] = pcm[k] / 32768;
        if (rms(f) > AGENT_RMS) {
          if (!agentActive && now - agentVoicedAt > 600) {
            const latency = youSpokeSinceAgent && lastYouVoiced ? now - lastYouVoiced : null;
            youSpokeSinceAgent = false;
            if (latency !== null) {
              setLines((ls) => {
                const idx = ls.map((l) => l.speaker === "agent" && l.latencyMs === null).lastIndexOf(true);
                if (idx < 0) return ls;
                const copy = [...ls];
                copy[idx] = { ...copy[idx], latencyMs: latency };
                return copy;
              });
            }
          }
          agentActive = true;
          agentVoicedAt = now;
          setAgentSpeaking(true);
        }
        const buf = ctx.createBuffer(1, FRAME, RATE);
        buf.copyToChannel(f, 0);
        const node = ctx.createBufferSource();
        node.buffer = buf;
        node.connect(ctx.destination);
        if (playHead < ctx.currentTime + 0.03) playHead = ctx.currentTime + 0.08;
        node.start(playHead);
        playHead += FRAME / RATE;
      };
    } catch (e) {
      const err = e as Error;
      setError(err.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow it from the browser address bar and try again."
        : err.message);
      setStatus("error");
      stop("error");
    }
  }, [stop]);

  return { status, error, lines, youLevel, agentSpeaking, headphones, setHeadphones, start, stop: () => stop("ended") };
}
