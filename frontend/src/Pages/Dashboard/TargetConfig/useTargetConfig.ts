import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { Diagnostic, Target } from "../../../api/types";

export interface TargetForm {
  name: string;
  adapter: "websocket_pcm" | "livekit";
  description: string;
  url: string;
  token: string;
  apiKey: string;
  apiSecret: string;
  room: string;
  llmPrompt: string;
  llmCompletion: string;
  ttsChars: string;
  sttMinute: string;
}

const empty: TargetForm = { name: "", adapter: "websocket_pcm", description: "", url: "", token: "", apiKey: "", apiSecret: "",
  room: "gauntlet-{call_id}", llmPrompt: "", llmCompletion: "", ttsChars: "", sttMinute: "" };

export function useTargetConfig() {
  const { id } = useParams();
  const isNew = !id;
  const qc = useQueryClient();
  const nav = useNavigate();
  const [form, setForm] = useState<TargetForm>(empty);
  const [fieldError, setFieldError] = useState<{ field?: string; message: string } | null>(null);
  const target = useQuery({ queryKey: ["target", id], queryFn: () => api.get<Target>(endpoints.target(id!)), enabled: !isNew });

  const set = <K extends keyof TargetForm>(k: K, v: TargetForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  const prices = () => {
    const n = (s: string) => (s.trim() === "" ? undefined : Number(s));
    const out: Record<string, Record<string, number>> = {};
    if (n(form.llmPrompt) !== undefined || n(form.llmCompletion) !== undefined)
      out.llm = { ...(n(form.llmPrompt) !== undefined ? { prompt_price_per_1k_tokens: n(form.llmPrompt)! } : {}),
        ...(n(form.llmCompletion) !== undefined ? { completion_price_per_1k_tokens: n(form.llmCompletion)! } : {}) };
    if (n(form.ttsChars) !== undefined) out.tts = { price_per_1k_characters: n(form.ttsChars)! };
    if (n(form.sttMinute) !== undefined) out.stt = { price_per_minute: n(form.sttMinute)! };
    return Object.keys(out).length ? out : undefined;
  };

  const connection = () => form.adapter === "websocket_pcm"
    ? { url: form.url, ...(form.token ? { token: form.token } : {}) }
    : { url: form.url, api_key: form.apiKey, api_secret: form.apiSecret, room: form.room };

  const save = useMutation({
    mutationFn: async () => {
      setFieldError(null);
      if (isNew) return api.post<Target>(endpoints.targets(), { name: form.name, adapter: form.adapter, description: form.description || undefined, connection: connection(), unit_prices: prices() });
      const body: Record<string, unknown> = { unit_prices: prices() };
      if (form.url) body.connection = connection();
      if (form.name) body.name = form.name;
      return api.patch<Target>(endpoints.target(id!), body);
    },
    onSuccess: (t) => {
      void qc.invalidateQueries({ queryKey: ["targets"] });
      void qc.invalidateQueries({ queryKey: ["target", t.id] });
      if (isNew) nav(`/dashboard/targets/${t.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError) setFieldError({ field: e.body?.field as string | undefined, message: e.message });
    },
  });

  const verify = useMutation({
    mutationFn: () => api.post<{ verified_at: string | null; failure_reason?: string }>(endpoints.verifyTarget(id!)),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["target", id] }),
  });
  const diagnose = useMutation({
    mutationFn: () => api.post<Diagnostic>(endpoints.diagnoseTarget(id!)),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["target", id] }),
  });

  return { isNew, target, form, set, save, verify, diagnose, fieldError };
}
