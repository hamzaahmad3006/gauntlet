import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "../../../api/client";

// The two bundled agent configurations (mirrors backend/gauntlet/db/seed.py BUNDLED_TARGETS).
export const AGENTS = {
  tuned: { label: "Tuned agent (fast)", query: "mode=reference&model=openai/gpt-oss-20b&endpoint_ms=450&delay_ms=250&yield_ms=220&greeting=1" },
  slow: { label: "Slow agent (badly tuned)", query: "mode=reference&model=openai/gpt-oss-120b&endpoint_ms=900&delay_ms=650&yield_ms=never&greeting=1" },
} as const;
export type AgentKey = keyof typeof AGENTS;

export interface TalkLine { speaker: "you" | "agent"; text: string | null; latencyMs: number | null; timings?: Record<string, number> }
type Status = "idle" | "connecting" | "live" | "ended" | "error";

const RATE = 16000;
const FRAME = 320; // 20 ms at 16 kHz, gauntlet.pcm.v1
const VOICE_RMS = 0.015; // about -36 dBFS, after the gain below
const TARGET_RMS = 0.06; // speech level the agent's recogniser expects
const MAX_GAIN = 30;
const GATE_OVER_FLOOR = 3; // speech is this much louder than the room
const GATE_MIN = 0.003; // and never quieter than this, whatever the room sounds like
const HANGOVER_MS = 700; // pauses inside a sentence are shorter than this, so a sentence stays whole
const MAX_GAIN_STEP = 0.05; // the gain moves slowly, so one keyboard tap cannot reset it
const AGENT_RMS = 0.01;

function wsUrl(query: string): string {
  const base = API_BASE || window.location.origin;
  return `${base.replace(/^http/, "ws")}/fixtures/agent?${query}`;
}

const rms = (x: Float32Array) => Math.sqrt(x.reduce((a, v) => a + v * v, 0) / x.length);

// Runs on the audio thread, so React renders on the page cannot starve playback. The player keeps a small
// queue and waits for ~100 ms of audio before it starts (and again after running dry), trading a little delay
// for gap-free sound; the capture node hands microphone blocks back to the page.
const WORKLET = `
class GauntletPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.q = []; this.head = null; this.pos = 0; this.queued = 0; this.playing = false;
    this.port.onmessage = (e) => {
      if (e.data === "flush") { this.q = []; this.head = null; this.pos = 0; this.queued = 0; this.playing = false; return; }
      this.q.push(e.data); this.queued += e.data.length;
      while (this.queued > 16000 && this.q.length > 1) { this.queued -= this.q.shift().length; }
    };
  }
  process(_inputs, outputs) {
    const out = outputs[0][0];
    if (!this.playing && this.queued < 1600) { out.fill(0); return true; }
    this.playing = true;
    for (let i = 0; i < out.length; i++) {
      if (!this.head || this.pos >= this.head.length) {
        this.head = this.q.shift() || null; this.pos = 0;
        if (!this.head) { out.fill(0, i); this.playing = false; this.queued = 0; return true; }
      }
      out[i] = this.head[this.pos++]; this.queued--;
    }
    return true;
  }
}
class GauntletCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("gauntlet-player", GauntletPlayer);
registerProcessor("gauntlet-capture", GauntletCapture);
`;

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
  const res = useRef<{ ctx?: AudioContext; ws?: WebSocket; stream?: MediaStream; nodes?: AudioNode[] }>({});

  const stop = useCallback((final: Status = "ended") => {
    const r = res.current;
    try {
      if (r.ws?.readyState === WebSocket.OPEN) r.ws.send(JSON.stringify({ type: "bye", reason: "user_hung_up" }));
    } catch { /* closing anyway */ }
    r.ws?.close();
    r.nodes?.forEach((n) => n.disconnect());
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
      const ctx = new AudioContext({ sampleRate: RATE, latencyHint: "interactive" });
      const moduleUrl = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(moduleUrl);
      URL.revokeObjectURL(moduleUrl);
      const player = new AudioWorkletNode(ctx, "gauntlet-player", { outputChannelCount: [1] });
      player.connect(ctx.destination);
      await ctx.resume();
      const ws = new WebSocket(wsUrl(AGENTS[agent].query));
      ws.binaryType = "arraybuffer";
      res.current = { ctx, ws, stream, nodes: [player] };

      let lastLevelPaint = 0;
      let lastYouVoiced = 0; // performance.now() of the last voiced microphone frame
      let youSpokeSinceAgent = false;
      let agentVoicedAt = 0;
      let agentActive = false;
      let pending = new Float32Array(0);
      // Laptop microphones arrive far quieter than the agent's recogniser expects — quiet enough that it
      // transcribes a whole sentence as ".". The gain follows the loudest recent frame towards a speech
      // level and only ever rises slowly, so a quiet microphone is usable and a loud one is not clipped.
      let gain = 1;
      let noiseFloor = 0.004; // the room, learned only while nobody is speaking
      let speechLevel = 0; // how loud this speaker is, from the loudest recent speech
      let lastSpeechAt = 0;
      let agentTurns = 0; // the greeting is never interrupted: a laptop speaker would cut it every time
      let latencyForNextReply: number | null = null; // measured before the reply's transcript arrived

      const beginMic = () => {
        const src = ctx.createMediaStreamSource(stream);
        const capture = new AudioWorkletNode(ctx, "gauntlet-capture", { numberOfOutputs: 0 });
        src.connect(capture);
        res.current.nodes = [...(res.current.nodes ?? []), src, capture];
        capture.port.onmessage = (ev: MessageEvent<Float32Array>) => {
          const input = ev.data;
          const merged = new Float32Array(pending.length + input.length);
          merged.set(pending);
          merged.set(input, pending.length);
          let i = 0;
          let loudest = 0;
          for (; i + FRAME <= merged.length; i += FRAME) {
            const frame = merged.subarray(i, i + FRAME);
            // without headphones the agent's own voice reaches the microphone: send silence while it talks
            const now = performance.now();
            const muted = (agentActive || now - agentVoicedAt < 400) && (!headphonesRef.current || agentTurns < 1);
            const raw = muted ? 0 : rms(frame);
            const speaking = !muted && raw > Math.max(noiseFloor * GATE_OVER_FLOOR, GATE_MIN);
            if (speaking) {
              lastSpeechAt = now;
              speechLevel = Math.max(raw, speechLevel * 0.995); // the loudest recent speech, decaying slowly
            } else {
              // the room is learned only in the gaps, so speech never drags the floor up behind it
              noiseFloor = raw < noiseFloor ? noiseFloor * 0.8 + raw * 0.2 : noiseFloor * 0.98 + raw * 0.02;
              speechLevel *= 0.999;
            }
            if (speechLevel > 0.0005) { // aim the speaker's own level at the recogniser's, one small step at a time
              const want = Math.min(MAX_GAIN, Math.max(1, TARGET_RMS / speechLevel));
              gain += Math.max(-MAX_GAIN_STEP, Math.min(MAX_GAIN_STEP, want - gain));
            }
            // pauses inside a sentence stay open; only a real gap becomes the silence that ends a turn
            const open = speaking || now - lastSpeechAt < HANGOVER_MS;
            const level = open ? Math.min(1, raw * gain) : 0;
            loudest = Math.max(loudest, level);
            if (level > VOICE_RMS) { lastYouVoiced = now; youSpokeSinceAgent = true; }
            const out = new Int16Array(FRAME);
            if (open) for (let k = 0; k < FRAME; k++) {
              const v = Math.max(-0.99, Math.min(0.99, frame[k] * gain));
              out[k] = Math.round(v * 32767);
            }
            if (ws.readyState === WebSocket.OPEN) ws.send(out.buffer);
          }
          pending = merged.slice(i);
          const t = performance.now();
          if (t - lastLevelPaint > 90) { lastLevelPaint = t; setYouLevel(loudest); } // ~11 paints a second, not 50
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
            const carried = heard.length ? latencyForNextReply : null;
            latencyForNextReply = null;
            setLines((ls) => [...ls, ...heard, { speaker: "agent", text: msg.said ?? null, latencyMs: carried, timings: msg.timings }]);
          }
          return;
        }
        const pcm = new Int16Array(ev.data as ArrayBuffer);
        if (pcm.length !== FRAME) return;
        let peak = 0;
        for (let k = 0; k < FRAME; k++) peak = Math.max(peak, Math.abs(pcm[k]));
        const now = performance.now();
        if (peak === 0) { // the agent's pacing silence
          if (agentActive && now - agentVoicedAt > 300) { agentActive = false; setAgentSpeaking(false); }
          if (agentActive) player.port.postMessage(new Float32Array(FRAME)); // pauses inside a reply keep their length
          return;
        }
        const f = new Float32Array(FRAME);
        for (let k = 0; k < FRAME; k++) f[k] = pcm[k] / 32768;
        if (rms(f) > AGENT_RMS) {
          if (!agentActive && now - agentVoicedAt > 600) {
            const latency = youSpokeSinceAgent && lastYouVoiced ? now - lastYouVoiced : null;
            youSpokeSinceAgent = false;
            if (latency !== null) {
              // the reply to the caller's latest words is the agent line after the latest "you" line
              latencyForNextReply = latency;
              setLines((ls) => {
                const lastYou = ls.map((l) => l.speaker === "you").lastIndexOf(true);
                const idx = ls.findIndex((l, j) => j > lastYou && lastYou >= 0 && l.speaker === "agent" && l.latencyMs === null);
                if (idx < 0) return ls;
                latencyForNextReply = null;
                const copy = [...ls];
                copy[idx] = { ...copy[idx], latencyMs: latency };
                return copy;
              });
            }
          }
          if (!agentActive) { setAgentSpeaking(true); agentTurns += 1; }
          agentActive = true;
          agentVoicedAt = now;
        }
        player.port.postMessage(f, [f.buffer]);
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
