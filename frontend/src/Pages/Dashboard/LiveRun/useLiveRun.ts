import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { CallStatus, ConditionProfile, LiveEvent, RunSummary } from "../../../api/types";

export interface Tile {
  id: string;
  scenario: string;
  persona: string;
  status: CallStatus | "connected";
  reason: string | null;
  latencies: (number | null)[];
  barges: number[];
  lastLatency: number | null;
}

export interface Line { turn: number; speaker: "caller" | "agent"; text: string | null; latency: number | null; referee: boolean; t: number }

export interface LatencyPoint { v: number; epoch: number; t: number }
export interface BargeEvent { call: string; turn: number; ms: number; noYield: boolean; t: number }

function nearest95(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.max(0, Math.ceil(0.95 * s.length) - 1)];
}

const TERMINAL = new Set(["completed", "aborted", "aborted_budget", "failed"]);

export function useLiveRun() {
  const { id } = useParams();
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: ["run", id], queryFn: () => api.get<RunSummary>(endpoints.run(id!)), refetchInterval: 4000 });
  const conditions = useQuery({ queryKey: ["conditions"], queryFn: () => api.get<ConditionProfile[]>(endpoints.conditionProfiles()) });
  const [tiles, setTiles] = useState<Record<string, Tile>>({});
  const [points, setPoints] = useState<LatencyPoint[]>([]);
  const [barges, setBarges] = useState<BargeEvent[]>([]);
  const [lines, setLines] = useState<Record<string, Line[]>>({});
  const [epochs, setEpochs] = useState<{ epoch: number; t: number; profile?: string }[]>([{ epoch: 0, t: 0 }]);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [spend, setSpend] = useState<number | null>(null);
  const [conn, setConn] = useState<"open" | "reconnecting" | "closed">("reconnecting");
  const [mode, setMode] = useState<"LIVE" | "REPLAY" | null>(null);
  const [finished, setFinished] = useState(false);
  const epochRef = useRef(0);
  const seen = useRef(new Set<string>());

  // Seed tiles from the summary so the grid is populated before any call connects.
  useEffect(() => {
    const s = summary.data;
    if (!s) return;
    if (mode === null) setMode(TERMINAL.has(s.run.status) ? "REPLAY" : "LIVE");
    setTiles((prev) => {
      const next = { ...prev };
      for (const c of s.calls) {
        if (!next[c.id]) next[c.id] = { id: c.id, scenario: c.scenario_key, persona: c.persona_key, status: mode === "REPLAY" ? "pending" : c.status, reason: c.reason_code, latencies: [], barges: [], lastLatency: null };
      }
      return next;
    });
  }, [summary.data, mode]);

  useEffect(() => {
    if (!mode) return;
    let queue: LiveEvent[] = [];
    let timer: ReturnType<typeof setTimeout> | null = null;
    const apply = (e: LiveEvent) => {
      if (seen.current.has(e.id)) return;
      seen.current.add(e.id);
      const t = typeof e.ts === "number" ? e.ts : Date.now();
      const cid = e.call_id as string | undefined;
      switch (e.kind) {
        case "caller.started":
          if (cid) setTiles((p) => ({ ...p, [cid]: { ...(p[cid] ?? { id: cid, scenario: String(e.scenario_key), persona: String(e.persona_key), latencies: [], barges: [], lastLatency: null, reason: null }), status: "dialling" } }));
          break;
        case "caller.connected":
          if (cid) setTiles((p) => (p[cid] ? { ...p, [cid]: { ...p[cid], status: "in_call" } } : p));
          break;
        case "metric.updated": {
          const lat = e.latency_ms as number | null;
          const barge = e.barge_stop_ms as number | null;
          if (cid) setTiles((p) => (p[cid] ? { ...p, [cid]: { ...p[cid], latencies: [...p[cid].latencies, lat], lastLatency: lat ?? p[cid].lastLatency, barges: barge != null ? [...p[cid].barges, barge] : p[cid].barges } } : p));
          if (lat != null) setPoints((p) => [...p, { v: lat, epoch: epochRef.current, t }]);
          if (barge != null && cid) setBarges((b) => [{ call: cid, turn: e.turn_idx as number, ms: barge, noYield: barge >= 2000, t }, ...b].slice(0, 40));
          break;
        }
        case "transcript.line":
          if (cid) {
            const line: Line = { turn: e.turn_idx as number, speaker: e.speaker as Line["speaker"], text: (e.text as string | null) ?? null,
              latency: (e.latency_ms as number | null) ?? null, referee: e.referee !== false, t };
            setLines((p) => ({ ...p, [cid]: [...(p[cid] ?? []), line] }));
          }
          break;
        case "caller.disconnected":
          if (cid) setTiles((p) => (p[cid] ? { ...p, [cid]: { ...p[cid], status: (e.status as CallStatus) === "scoring" ? "scoring" : (e.status as CallStatus), reason: (e.reason_code as string) ?? null } } : p));
          break;
        case "evaluation.completed":
          if (cid) setTiles((p) => (p[cid] ? { ...p, [cid]: { ...p[cid], status: e.needs_review ? "needs_review" : e.task_success === false ? "failed" : "completed" } } : p));
          break;
        case "chaos.changed":
          epochRef.current = e.epoch as number;
          setEpochs((x) => [...x, { epoch: e.epoch as number, t, profile: (e.profile as string) ?? undefined }]);
          break;
        case "spend.updated":
          setSpend(e.rig_cost_usd as number);
          break;
        case "run.progress":
          setProgress({ completed: e.completed as number, failed: e.failed as number, errored: e.errored as number, needs_review: e.needs_review as number, total: e.total as number, active: e.active as number, peak: e.peak_concurrency as number });
          break;
        case "run.completed":
        case "run.failed":
          setFinished(true);
          void qc.invalidateQueries({ queryKey: ["run", id] });
          break;
      }
    };
    // REPLAY paces stored events by their wall-clock gaps at 8x; LIVE applies them immediately.
    const pump = () => {
      timer = null;
      const e = queue.shift();
      if (!e) return;
      apply(e);
      const nxt = queue[0];
      const gap = nxt && typeof nxt.ts === "number" && typeof e.ts === "number" ? Math.min(1500, Math.max(0, (nxt.ts - e.ts) / 8)) : 0;
      if (nxt) timer = setTimeout(pump, gap);
    };
    const stop = api.stream(endpoints.events(id!), (e) => {
      if (mode === "LIVE") apply(e);
      else {
        queue.push(e);
        if (!timer) timer = setTimeout(pump, 0);
      }
    }, setConn);
    return () => {
      stop();
      if (timer) clearTimeout(timer);
      queue = [];
    };
  }, [id, mode, qc]);

  const inject = useMutation({
    mutationFn: (profile_key: string) => api.post<{ epoch: number }>(endpoints.conditions(id!), { profile_key }),
  });
  const abort = useMutation({ mutationFn: () => api.post(endpoints.abort(id!)), onSuccess: () => void qc.invalidateQueries({ queryKey: ["run", id] }) });

  const rolling = useMemo(() => {
    const out: { p95: number; epoch: number }[] = [];
    for (let i = 0; i < points.length; i++) {
      const w = points.slice(Math.max(0, i - 19), i + 1).map((p) => p.v);
      out.push({ p95: nearest95(w)!, epoch: points[i].epoch });
    }
    return out;
  }, [points]);
  const byEpoch = useMemo(() => {
    const m = new Map<number, number[]>();
    points.forEach((p) => m.set(p.epoch, [...(m.get(p.epoch) ?? []), p.v]));
    return [...m.entries()].map(([epoch, vs]) => ({ epoch, n: vs.length, p95: nearest95(vs) }));
  }, [points]);

  return { id: id!, summary, conditions, tiles: Object.values(tiles), lines, rolling, byEpoch, barges, epochs, progress, spend, conn, mode, finished, inject, abort };
}
